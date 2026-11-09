"""Cancelable back/forward walking with no dependency on a desktop session."""

import math
import threading


class WalkEngine(threading.Thread):
    """Hold S, hold W, then wait the configured gap before the next cycle."""

    def __init__(self, press, release):
        super().__init__(daemon=True)
        self._press = press
        self._release = release
        self._condition = threading.Condition()
        self._cancel = None
        self._held = None
        self._alive = True
        self._interval = 30.0
        self._forward_seconds = 1.0
        self.error = None

    @property
    def active(self):
        with self._condition:
            return self._cancel is not None and not self._cancel.is_set()

    @property
    def interval(self):
        with self._condition:
            return self._interval

    @interval.setter
    def interval(self, seconds):
        seconds = float(seconds)
        if not math.isfinite(seconds) or not 0.1 <= seconds <= 86400:
            raise ValueError("Enter a wait from 0.1 seconds to 24 hours.")
        with self._condition:
            self._interval = seconds

    @property
    def forward_seconds(self):
        with self._condition:
            return self._forward_seconds

    @forward_seconds.setter
    def forward_seconds(self, seconds):
        seconds = float(seconds)
        if not math.isfinite(seconds) or not 0.1 <= seconds <= 10:
            raise ValueError("Enter a return time from 0.1 to 10 seconds.")
        with self._condition:
            self._forward_seconds = seconds

    def start_walking(self, delay=0, once=False):
        with self._condition:
            if not self._alive or self.active:
                return
            self._release_held()
            if self._held is not None:
                return
            self.error = None
            self._cancel = threading.Event()
            self._delay = delay
            self._once = once
            self._condition.notify()

    def stop_walking(self):
        with self._condition:
            if self._cancel is not None:
                self._cancel.set()
            self._release_held()

    def _release_held(self):
        if self._held is not None:
            key = self._held
            try:
                self._release(key)
            except Exception as exc:
                self.error = str(exc)
                if self._cancel is not None:
                    self._cancel.set()
            else:
                self._held = None

    def _hold(self, key, cancel, seconds=1.0):
        with self._condition:
            if cancel.is_set():
                return False
            self._held = key
            self._press(key)
        cancel.wait(seconds)
        with self._condition:
            self._release_held()
        return not cancel.is_set()

    def run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: not self._alive or self.active)
                if not self._alive:
                    return
                cancel, delay, once = self._cancel, self._delay, self._once
            try:
                if cancel.wait(delay):
                    continue
                while not cancel.is_set():
                    forward_seconds = self.forward_seconds
                    if not self._hold("s", cancel):
                        break
                    if not self._hold("w", cancel, forward_seconds):
                        break
                    if once:
                        cancel.set()
                        break
                    cancel.wait(self.interval)
            except Exception as exc:
                self.error = str(exc)
                cancel.set()
            finally:
                with self._condition:
                    self._release_held()

    def shutdown(self):
        with self._condition:
            self._alive = False
            self.stop_walking()
            self._condition.notify()
