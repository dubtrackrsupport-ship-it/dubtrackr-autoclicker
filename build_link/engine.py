"""DubTrackr build link: the input half of "Build it for me" in the DubTrackr app.

The DubTrackr app is the brain. It knows the build, reads the game and plans every step. This
engine only turns short, bounded steps into keyboard and mouse input, and owns every safety stop,
so they still work if the app hangs or is killed:

* No input unless the target game (Minecraft for Windows) is the foreground window and has the
  mouse captured (cursor hidden). A visible cursor means a screen is open: chat, pause menu,
  inventory, a sign. That stops the build.
* Any real key press, click or mouse movement from the player stops it. So does the stop hotkey
  (F9 by default).
* The brain sends a heartbeat. 500 ms without one stops the build (watchdog).
* Every stop releases every key and button the engine holds. A movement key is never held longer
  than MAX_HOLD_S. Only sneak may stay down between steps, and it is released on every stop.
* After a stop the engine stays disarmed until the brain arms it again (the player presses
  Resume in the app).

Speeds are human-plausible by default, for reliability and courtesy. Nothing here hides or
disguises the input: servers can detect it, and the app warns the player about that.
"""

import threading
import time

KEYS = ("w", "a", "s", "d", "space", "shift", "1", "2", "3", "4", "5", "6", "7", "8", "9")
BUTTONS = ("left", "right")
MAX_HOLD_S = 2.0          # longest a key or button is held in one go (sneak excepted)
MAX_STEP_MS = 2000        # longest single hold or wait the brain may ask for
MAX_MOUSE = 4000          # largest relative mouse move in one action, in counts
MAX_ACTIONS = 64          # actions in one step
WATCHDOG_S = 0.5
MONITOR_S = 0.01
MOUSE_JITTER_COUNTS = 2   # real mouse movement below this in one report is not counted
RATES = {
    # min gap between click starts, mouse counts per second, gap between mouse slices
    "normal": {"click_gap": 0.18, "mouse_cps": 2400, "slice": 0.008},
    "fast": {"click_gap": 0.08, "mouse_cps": 6000, "slice": 0.004},
}

STOP_REASONS = {
    "hotkey": "You pressed the stop key.",
    "input": "You used the keyboard or mouse, so the build stopped.",
    "focus": "Minecraft is no longer the window in front.",
    "screen": "A screen opened in Minecraft (chat, pause menu or inventory).",
    "watchdog": "The DubTrackr app stopped answering.",
    "busy": "Another AutoClickr automation is running.",
    "disconnect": "The DubTrackr app disconnected.",
    "brain": "The DubTrackr app stopped the build.",
    "error": "Input could not be sent.",
    "shutdown": "AutoClickr is closing.",
}


class StepError(ValueError):
    """A step the engine refuses (bad shape or out of bounds)."""


def validate_actions(actions):
    """Checks a step's actions; returns them as tidy dicts or raises StepError."""
    if not isinstance(actions, list) or not actions or len(actions) > MAX_ACTIONS:
        raise StepError("a step needs 1 to %d actions" % MAX_ACTIONS)
    out = []
    for a in actions:
        if not isinstance(a, dict):
            raise StepError("action is not an object")
        k = a.get("k")
        ms = a.get("ms", 0)
        if not isinstance(ms, (int, float)) or ms != ms or not 0 <= ms <= MAX_STEP_MS:
            raise StepError("ms out of range")
        if k in ("down", "up", "hold", "tap"):
            if a.get("key") not in KEYS:
                raise StepError("unknown key")
            if k == "down" and a["key"] != "shift":
                # Only sneak stays held between actions; movement is always a bounded hold.
                raise StepError("only shift can be held down between actions")
            out.append({"k": k, "key": a["key"], "ms": ms if k == "hold" else (40 if k == "tap" else 0)})
        elif k == "mouse":
            dx, dy = a.get("dx", 0), a.get("dy", 0)
            if not all(isinstance(v, int) and not isinstance(v, bool) and abs(v) <= MAX_MOUSE for v in (dx, dy)):
                raise StepError("mouse move out of range")
            out.append({"k": "mouse", "dx": dx, "dy": dy})
        elif k == "click":
            if a.get("button") not in BUTTONS:
                raise StepError("unknown button")
            out.append({"k": "click", "button": a["button"], "ms": ms or 50})
        elif k == "wait":
            out.append({"k": "wait", "ms": ms})
        else:
            raise StepError("unknown action")
    return out


class Stopped(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class BuildEngine:
    """Runs validated steps through a backend and enforces every stop.

    backend must provide: key_down(name), key_up(name), button_down(name), button_up(name),
    mouse_move(dx, dy), target_state() -> "ok" | "focus" | "screen", and may provide
    start_watch(on_real_input, on_hotkey) / stop_watch() for the player's own input.
    """

    def __init__(self, backend, busy=lambda: False, clock=time.monotonic, watchdog_s=WATCHDOG_S,
                 on_event=lambda event: None):
        self._b = backend
        self._busy = busy
        self._clock = clock
        self._watchdog_s = watchdog_s
        self._on_event = on_event
        self._lock = threading.RLock()
        self._armed = False
        self._stop = threading.Event()
        self._stop.set()
        self._held_keys = {}      # name -> time pressed
        self._held_buttons = {}
        self._last_beat = 0.0
        self._last_click = -1e9
        self._rate = RATES["normal"]
        self._reason = None
        self._alive = True
        self._monitor = threading.Thread(target=self._watch, daemon=True, name="build-link-monitor")
        self._monitor.start()
        if hasattr(backend, "start_watch"):
            backend.start_watch(lambda: self.stop("input"), lambda: self.stop("hotkey"))

    # ----- state -----
    @property
    def armed(self):
        with self._lock:
            return self._armed

    @property
    def reason(self):
        with self._lock:
            return self._reason

    def held(self):
        with self._lock:
            return sorted(self._held_keys) + ["mouse:" + b for b in sorted(self._held_buttons)]

    def arm(self, rate="normal"):
        """Starts a build session. Returns None, or the reason it cannot start."""
        with self._lock:
            if not self._alive:
                return "shutdown"
            if self._busy():
                return "busy"
            state = self._b.target_state()
            if state != "ok":
                return state
            self._rate = RATES.get(rate, RATES["normal"])
            self._release_all()
            self._armed = True
            self._reason = None
            self._last_beat = self._clock()
            self._stop.clear()
        return None

    def beat(self):
        with self._lock:
            self._last_beat = self._clock()

    def stop(self, reason="brain"):
        """Disarms and releases everything. Safe to call from any thread, any number of times."""
        with self._lock:
            was = self._armed
            self._armed = False
            self._stop.set()
            self._release_all()
            if was:
                self._reason = reason
        if was:
            try:
                self._on_event({"event": "stopped", "reason": reason, "text": STOP_REASONS.get(reason, reason)})
            except Exception:
                pass

    def shutdown(self):
        self.stop("shutdown")
        with self._lock:
            self._alive = False
        if hasattr(self._b, "stop_watch"):
            try:
                self._b.stop_watch()
            except Exception:
                pass
        self._monitor.join(1)

    # ----- running a step -----
    def run(self, actions):
        """Runs one step's actions in order. Raises Stopped(reason) if the build stops meanwhile."""
        actions = validate_actions(actions)
        for a in actions:
            k = a["k"]
            if k == "down":
                self._press_key(a["key"])
            elif k == "up":
                self._release_key(a["key"])
            elif k in ("hold", "tap"):
                self._press_key(a["key"])
                try:
                    self._sleep(min(a["ms"] / 1000.0, MAX_HOLD_S))
                finally:
                    self._release_key(a["key"])
            elif k == "mouse":
                self._mouse(a["dx"], a["dy"])
            elif k == "click":
                wait = self._rate["click_gap"] - (self._clock() - self._last_click)
                if wait > 0:
                    self._sleep(wait)
                self._press_button(a["button"])
                self._last_click = self._clock()
                try:
                    self._sleep(min(a["ms"] / 1000.0, MAX_HOLD_S))
                finally:
                    self._release_button(a["button"])
            elif k == "wait":
                self._sleep(a["ms"] / 1000.0)
        self._gate()

    def _gate(self):
        with self._lock:
            if not self._armed:
                raise Stopped(self._reason or "brain")
            state = self._b.target_state()
        if state != "ok":
            self.stop(state)
            raise Stopped(state)

    def _sleep(self, seconds):
        if seconds > 0 and self._stop.wait(seconds):
            raise Stopped(self.reason or "brain")
        self._gate()

    def _send(self, fn, *args):
        self._gate()
        with self._lock:
            if not self._armed:
                raise Stopped(self._reason or "brain")
            try:
                fn(*args)
            except Exception:
                self._armed_error()
                raise Stopped("error")

    def _armed_error(self):
        # Called with the lock held.
        self._armed = False
        self._stop.set()
        self._release_all()
        self._reason = "error"

    def _press_key(self, name):
        def go(n):
            self._b.key_down(n)
            self._held_keys[n] = self._clock()
        self._send(go, name)

    def _release_key(self, name):
        with self._lock:
            if name in self._held_keys:
                self._held_keys.pop(name, None)
                try:
                    self._b.key_up(name)
                except Exception:
                    pass

    def _press_button(self, name):
        def go(n):
            self._b.button_down(n)
            self._held_buttons[n] = self._clock()
        self._send(go, name)

    def _release_button(self, name):
        with self._lock:
            if name in self._held_buttons:
                self._held_buttons.pop(name, None)
                try:
                    self._b.button_up(name)
                except Exception:
                    pass

    def _mouse(self, dx, dy):
        """A relative move, sliced so it turns at the session's rate."""
        total = max(abs(dx), abs(dy))
        if not total:
            return
        per_slice = max(1, int(self._rate["mouse_cps"] * self._rate["slice"]))
        slices = max(1, -(-total // per_slice))
        sent_x = sent_y = 0
        for i in range(1, slices + 1):
            tx = round(dx * i / slices)
            ty = round(dy * i / slices)
            self._send(self._b.mouse_move, tx - sent_x, ty - sent_y)
            sent_x, sent_y = tx, ty
            if i < slices:
                self._sleep(self._rate["slice"])

    def _release_all(self):
        # Called with the lock held. Never raises.
        for name in list(self._held_keys):
            self._held_keys.pop(name, None)
            try:
                self._b.key_up(name)
            except Exception:
                pass
        for name in list(self._held_buttons):
            self._held_buttons.pop(name, None)
            try:
                self._b.button_up(name)
            except Exception:
                pass

    # ----- the monitor -----
    def _watch(self):
        while True:
            with self._lock:
                if not self._alive:
                    return
                armed = self._armed
                beat_age = self._clock() - self._last_beat
                now = self._clock()
                overheld = [n for n, t in self._held_keys.items() if n != "shift" and now - t > MAX_HOLD_S + 0.2]
                overheld += ["mouse:" + n for n, t in self._held_buttons.items() if now - t > MAX_HOLD_S + 0.2]
            if armed:
                reason = None
                if beat_age > self._watchdog_s:
                    reason = "watchdog"
                elif overheld:
                    reason = "error"
                elif self._busy():
                    reason = "busy"
                else:
                    try:
                        state = self._b.target_state()
                    except Exception:
                        state = "focus"
                    if state != "ok":
                        reason = state
                if reason:
                    self.stop(reason)
            time.sleep(MONITOR_S)
