"""
DubTrackr AutoClickr  —  Dual HUD
==================================
A lightweight dual-engine autoclicker with dubtrackr branding.

  * Independent MOUSE and KEYBOARD engines, each with its own toggle hotkey.
  * Adjustable interval (ms) / CPS with human-like randomized jitter.
  * Mouse: left/right/middle, single or double click.
  * Keyboard: tap-repeat OR hold-down any key (space, w, a, s, d, ...).
  * Droid Tycoon scrap-table/crafting preset.
  * Windows 11 light / dark (follows system) + accent theme picker.
  * Settings persist between launches.

Free & open source — part of the Dubtrackr Network · https://www.dubtrackr.win
Requires:  pip install customtkinter pynput
"""

import colorsys
import json
import os
import random
import sys
import threading
import tkinter as tk
import webbrowser

import customtkinter as ctk
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import (Controller as KeyboardController, Key,
                             Listener as KeyListener)
from version import VERSION

APP_NAME = "DubTrackr AutoClickr"
WEBSITE = "https://www.dubtrackr.win"

# ---- brand palette (from dubtrackr.win) ----
BRAND_A = "#39a8ff"          # gradient start (cyan)
BRAND_B = "#824cf2"          # gradient end (violet)
GRAD_MID = "#4f72f5"         # solid stand-in for the brand gradient
COL_STOP = "#ff695f"         # coral  = stop / running-mouse
COL_GO = "#3bdda1"           # green  = go / running
NAVY = "#020814"
NAVY_DEEP = "#01050d"

ACCENTS = {
    "Gradient": GRAD_MID,
    "Green": COL_GO,
    "Coral": COL_STOP,
    "Amber": "#ffb43b",
}

# keyboard rate units -> milliseconds
UNITS = {"ms": 1, "sec": 1000, "min": 60000}

# each template themes the accent AND the header banner's two gradient colors
BANNERS = {
    "Gradient": ("#39a8ff", "#824cf2"),   # brand: cyan -> violet
    "Green":    ("#3bdda1", "#2f7ff2"),   # mint -> blue
    "Coral":    ("#ff8a5f", "#ff5f9e"),   # coral -> pink
    "Amber":    ("#ffce3b", "#ff7a3b"),   # gold -> orange
}

def resource_path(rel):
    """Path to a bundled resource, working both from source and a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


mouse = MouseController()
kbd = KeyboardController()

# Windows defaults to a ~15.6ms timer tick, which quantizes sleeps and makes
# clicking feel uneven. Raise the system timer resolution to 1ms while running.
_winmm = None
if sys.platform == "win32":
    try:
        import ctypes
        _winmm = ctypes.WinDLL("winmm")
    except Exception:
        _winmm = None


def timer_begin():
    if _winmm:
        try:
            _winmm.timeBeginPeriod(1)
        except Exception:
            pass


def timer_end():
    if _winmm:
        try:
            _winmm.timeEndPeriod(1)
        except Exception:
            pass

# keys we inject ourselves (so the hotkey listener ignores them)
_injecting = set()
_inject_lock = threading.Lock()

BUTTONS = {"Left": Button.left, "Right": Button.right, "Middle": Button.middle}
SPECIAL_KEYS = {
    "space": Key.space, "enter": Key.enter, "tab": Key.tab, "shift": Key.shift,
    "ctrl": Key.ctrl, "alt": Key.alt, "esc": Key.esc, "backspace": Key.backspace,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4, "f5": Key.f5,
    "f6": Key.f6, "f7": Key.f7, "f8": Key.f8, "f9": Key.f9, "f10": Key.f10,
}

SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                            "DubtrackrAutoClicker")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULTS = {
    "appearance": "System", "accent": "Gradient",
    "m_button": "Left", "m_double": False, "m_interval": 1000, "m_jitter": 5,
    "m_hotkey": "f6",
    "k_key": "space", "k_hold": False, "k_interval": 200, "k_unit": "ms",
    "k_jitter": 10, "k_hotkey": "f7",
}


def parse_key(text):
    text = (text or "").strip().lower()
    if text in SPECIAL_KEYS:
        return SPECIAL_KEYS[text]
    return text[0] if text else None


def key_label(k):
    if isinstance(k, Key):
        return k.name
    if hasattr(k, "char") and k.char:
        return k.char
    return str(k).strip("'")


def key_from_name(name):
    name = (name or "").lower()
    return SPECIAL_KEYS.get(name, name[:1] if name else None)


def darken(hex_color, f=0.82):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * f), int(g * f), int(b * f))


def derive_shade(hex_color, deg=26):
    """A harmonious sibling of a color — same tone, hue nudged (keyboard side)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
    hh = (hh + deg / 360.0) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hh, ss, vv)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


class RepeatEngine(threading.Thread):
    """Timed-repeat worker. `action` runs every interval while active."""

    def __init__(self, action):
        super().__init__(daemon=True)
        self.action = action
        self.running = threading.Event()
        self._pause = threading.Event()   # set => wake the inter-click sleep at once
        self.alive = True
        self.interval = 0.15
        self.jitter = 0.10

    def next_delay(self):
        if self.jitter <= 0:
            return self.interval
        spread = self.interval * self.jitter
        return max(0.001, self.interval + random.uniform(-spread, spread))

    def run(self):
        while self.alive:
            self.running.wait()          # block (no busy poll) until active
            if not self.alive:
                break
            try:
                self.action()
            except Exception:
                pass
            # one precise wait per interval; returns immediately if stopped
            self._pause.wait(self.next_delay())

    def start_clicking(self):
        self._pause.clear()
        self.running.set()

    def stop_clicking(self):
        self.running.clear()
        self._pause.set()                # break any in-progress sleep now

    def toggle(self):
        if self.running.is_set():
            self.stop_clicking()
        else:
            self.start_clicking()
        return self.running.is_set()

    def shutdown(self):
        self.alive = False
        self.running.set()               # release running.wait()
        self._pause.set()                # release the sleep


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        timer_begin()               # 1ms system timer for smooth, precise clicking
        self.s = load_settings()
        ctk.set_appearance_mode(self.s["appearance"])
        ctk.set_default_color_theme("blue")

        self.accent = ACCENTS.get(self.s["accent"], GRAD_MID)
        self.accent2 = derive_shade(self.accent)   # keyboard-side sibling shade
        self.banner_a, self.banner_b = BANNERS.get(self.s["accent"], (BRAND_A, BRAND_B))
        self.title(APP_NAME)
        self.geometry("560x500")
        self._set_icon()

        self.mouse_engine = RepeatEngine(self.do_mouse_click)
        self.key_engine = RepeatEngine(self.do_key_action)
        self.mouse_engine.start()
        self.key_engine.start()

        self.mouse_hotkey = key_from_name(self.s["m_hotkey"])
        self.key_hotkey = key_from_name(self.s["k_hotkey"])
        self.capture_target = None
        self._held_key = None

        self._build()
        self._apply_settings_to_ui()
        self._refresh_cps()
        self._autosize()

        self.listener = KeyListener(on_press=self.on_global_key)
        self.listener.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- icon ----------
    def _set_icon(self):
        try:
            path = resource_path("dubtrackr.ico")
            if os.path.exists(path):
                self.iconbitmap(path)
        except Exception:
            pass

    # ---------- engine actions ----------
    def do_mouse_click(self):
        mouse.click(BUTTONS[self.s["m_button"]], 2 if self.s["m_double"] else 1)

    def do_key_action(self):
        k = parse_key(self.s["k_key"])
        if k is None:
            return
        with _inject_lock:
            _injecting.add(k)
        if self.s["k_hold"]:
            kbd.press(k)                # hold: press once, released on stop
            self._held_key = k
            self.key_engine.stop_clicking()   # nothing more to repeat
            self.after(0, self._sync_key_running)
        else:
            kbd.press(k)
            kbd.release(k)
        with _inject_lock:
            _injecting.discard(k)

    def _release_held(self):
        if self._held_key is not None:
            try:
                kbd.release(self._held_key)
            except Exception:
                pass
            self._held_key = None

    # ================= UI =================
    def _autosize(self):
        """Shrink the window to exactly fit its content (no dead space)."""
        self.update_idletasks()
        h = self.winfo_reqheight()
        self.geometry(f"560x{h}")
        self.minsize(520, h)

    def _build(self):
        self._build_header()

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(12, 6))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="col")
        grid.grid_rowconfigure(0, weight=0)

        self._build_mouse(grid)
        self._build_keyboard(grid)
        self._build_footer()

    def _build_header(self):
        head = tk.Frame(self, height=76, bg=NAVY_DEEP)
        head.pack(fill="x")
        head.pack_propagate(False)
        cv = tk.Canvas(head, height=76, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        self._header_canvas = cv
        self._logo_img = None
        try:
            self._logo_img = tk.PhotoImage(file=resource_path("assets/logo-header.png"))
        except Exception:
            self._logo_img = None
        cv.bind("<Configure>", self._paint_header)

    def _paint_header(self, event=None):
        cv = self._header_canvas
        w = cv.winfo_width() or 560
        h = 76
        cv.delete("all")
        # solid dark brand surface (matches dubtrackr.win)
        cv.create_rectangle(0, 0, w, h, fill=NAVY, outline="")
        # brand mark (white-element variant reads on the dark surface)
        if self._logo_img is not None:
            cv.create_image(38, 38, image=self._logo_img)
        else:
            cv.create_text(38, 38, text="D", fill="#ffffff",
                           font=("Segoe UI Black", 20, "bold"))
        # wordmark: Dub (white) Trackr (preset color 1) Auto (white) Clickr (preset color 2)
        f = ("Segoe UI Black", 15)
        seg = cv.create_text(68, 29, text="Dub", anchor="w", fill="#ffffff", font=f)
        seg = cv.create_text(cv.bbox(seg)[2], 29, text="Trackr", anchor="w",
                             fill=self.banner_a, font=f)
        seg = cv.create_text(cv.bbox(seg)[2], 29, text=" Auto", anchor="w",
                             fill="#ffffff", font=f)
        cv.create_text(cv.bbox(seg)[2], 29, text="Clickr", anchor="w",
                       fill=self.banner_b, font=f)
        cv.create_text(69, 51, text="part of the dubtrackr network", anchor="w",
                       fill="#5f6f86", font=("Segoe UI", 9))
        link = cv.create_text(w - 18, 38, text="dubtrackr.win  ↗", anchor="e",
                              fill=self.accent, font=("Segoe UI Semibold", 11, "bold"))
        cv.tag_bind(link, "<Button-1>", lambda e: webbrowser.open(WEBSITE))
        cv.tag_bind(link, "<Enter>", lambda e: cv.config(cursor="hand2"))
        cv.tag_bind(link, "<Leave>", lambda e: cv.config(cursor=""))

    def _module_frame(self, parent, col, title):
        f = ctk.CTkFrame(parent, corner_radius=14)
        f.grid(row=0, column=col, sticky="new", padx=(0, 8) if col == 0 else (8, 0))
        ctk.CTkLabel(f, text=title, font=("Segoe UI", 11, "bold"),
                     text_color=("#6b7a92", "#9dadc2")).pack(anchor="w", padx=16, pady=(14, 0))
        return f

    def _build_mouse(self, grid):
        f = self._module_frame(grid, 0, "◆  MOUSE")

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(2, 8))
        self.m_cps_lbl = ctk.CTkLabel(row, text="6.7", font=("Cascadia Mono", 34, "bold"),
                                      text_color=self.accent)
        self.m_cps_lbl.pack(side="left")
        self.m_state_lbl = ctk.CTkLabel(row, text="CPS\nIDLE", font=("Segoe UI", 9, "bold"),
                                        justify="left", text_color=("#6b7a92", "#9dadc2"))
        self.m_state_lbl.pack(side="left", padx=(8, 0))

        self.m_button = ctk.CTkOptionMenu(f, values=list(BUTTONS),
                                          command=lambda _v: self._on_change(), width=110,
                                          fg_color=self.accent, button_color=darken(self.accent),
                                          button_hover_color=darken(self.accent, 0.7))
        self.m_button.pack(anchor="w", padx=16, pady=3)
        self.m_click = ctk.CTkSegmentedButton(f, values=["Single", "Double"],
                                              selected_color=self.accent,
                                              selected_hover_color=darken(self.accent),
                                              command=lambda _v: self._on_change())
        self.m_click.pack(fill="x", padx=16, pady=3)

        self._labeled(f, "CPS", "m_cps_e", "6.7", self._on_change)
        self._jitter_row(f, "m_jitter_e", "m_jitter_ms")

        hk = ctk.CTkFrame(f, fg_color="transparent")
        hk.pack(fill="x", padx=16, pady=(6, 4))
        ctk.CTkLabel(hk, text="Hotkey", font=("Segoe UI", 11),
                     text_color=("#6b7a92", "#9dadc2")).pack(side="left")
        self.m_hotkey_btn = ctk.CTkButton(hk, text="F6", width=64, height=26,
                                          fg_color=("#e6ecf6", "#0b1a30"),
                                          text_color=self.accent,
                                          hover_color=("#d7e0ee", "#132444"),
                                          command=lambda: self._begin_capture("mouse"))
        self.m_hotkey_btn.pack(side="right")

        self.m_start = ctk.CTkButton(f, text="▶  Start", height=40,
                                     font=("Segoe UI Semibold", 14, "bold"),
                                     fg_color=self.accent, hover_color=darken(self.accent),
                                     command=self.toggle_mouse)
        self.m_start.pack(fill="x", padx=16, pady=(8, 14))

    def _build_keyboard(self, grid):
        f = self._module_frame(grid, 1, "◆  KEYBOARD")

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(2, 8))
        self.k_cps_lbl = ctk.CTkLabel(row, text="5.0", font=("Cascadia Mono", 34, "bold"),
                                      text_color=self.accent2)
        self.k_cps_lbl.pack(side="left")
        self.k_state_lbl = ctk.CTkLabel(row, text="EVERY\nIDLE", font=("Segoe UI", 9, "bold"),
                                        justify="left", text_color=("#6b7a92", "#9dadc2"))
        self.k_state_lbl.pack(side="left", padx=(8, 0))

        self._labeled(f, "Key", "k_key_e", "space", self._on_change, mono=False)
        self.k_mode = ctk.CTkSegmentedButton(f, values=["Tap", "Hold"],
                                             selected_color=self.accent2,
                                             selected_hover_color=darken(self.accent2),
                                             command=lambda _v: self._on_mode_change())
        self.k_mode.pack(fill="x", padx=16, pady=3)

        # single "Every [value] [unit]" control — e.g. every 20 sec
        self.k_every_row = ctk.CTkFrame(f, fg_color="transparent")
        self.k_every_row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(self.k_every_row, text="Every", font=("Segoe UI", 11),
                     text_color=("#6b7a92", "#9dadc2")).pack(side="left")
        self.k_unit = ctk.CTkOptionMenu(self.k_every_row, values=list(UNITS), width=70,
                                        fg_color=self.accent2, button_color=darken(self.accent2),
                                        button_hover_color=darken(self.accent2, 0.7),
                                        command=lambda _v: self._on_change())
        self.k_unit.pack(side="right")
        self.k_every_e = ctk.CTkEntry(self.k_every_row, width=70, justify="right",
                                      font=("Cascadia Mono", 12))
        self.k_every_e.pack(side="right", padx=(0, 8))
        self.k_every_e.bind("<KeyRelease>", lambda _ev: self._on_change())

        self._jitter_row(f, "k_jitter_e", "k_jitter_ms")

        hk = ctk.CTkFrame(f, fg_color="transparent")
        hk.pack(fill="x", padx=16, pady=(6, 4))
        ctk.CTkLabel(hk, text="Hotkey", font=("Segoe UI", 11),
                     text_color=("#6b7a92", "#9dadc2")).pack(side="left")
        self.k_hotkey_btn = ctk.CTkButton(hk, text="F7", width=64, height=26,
                                          fg_color=("#e6ecf6", "#0b1a30"),
                                          text_color=self.accent2,
                                          hover_color=("#d7e0ee", "#132444"),
                                          command=lambda: self._begin_capture("key"))
        self.k_hotkey_btn.pack(side="right")

        self.k_start = ctk.CTkButton(f, text="▶  Start", height=40,
                                     font=("Segoe UI Semibold", 14, "bold"),
                                     fg_color=self.accent2, hover_color=darken(self.accent2),
                                     command=self.toggle_key)
        self.k_start.pack(fill="x", padx=16, pady=(8, 14))

    def _build_footer(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(4, 14))

        ctk.CTkButton(bar, text="⚡ Droid Tycoon scrap/craft", width=190, height=30,
                      fg_color=("#e6ecf6", "#0b1a30"), text_color=("#334", "#cdd9ec"),
                      hover_color=("#d7e0ee", "#132444"),
                      command=self.apply_droid_tycoon_preset).pack(side="left")

        self.appearance = ctk.CTkSegmentedButton(
            bar, values=["System", "Light", "Dark"],
            command=self._on_appearance, width=180)
        self.appearance.pack(side="left", padx=10)

        # 4 template swatches — each shows its two banner colors; click re-themes
        # the accent + the header banner gradient
        sw = ctk.CTkFrame(bar, fg_color="transparent")
        sw.pack(side="right")
        self._swatch = {}
        for name in BANNERS:
            cv = tk.Canvas(sw, width=22, height=22, highlightthickness=0, bd=0,
                           cursor="hand2")
            cv.pack(side="left", padx=3)
            cv.bind("<Button-1>", lambda _e, n=name: self._set_accent(n))
            self._swatch[name] = cv

    def _labeled(self, parent, label, attr, default, cmd, mono=True):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 11),
                     text_color=("#6b7a92", "#9dadc2")).pack(side="left")
        e = ctk.CTkEntry(row, width=78, justify="right",
                         font=("Cascadia Mono", 12) if mono else ("Segoe UI", 12))
        e.insert(0, default)
        e.pack(side="right")
        e.bind("<KeyRelease>", lambda _ev: cmd())
        setattr(self, attr, e)

    def _jitter_row(self, parent, attr, ms_attr):
        """Jitter (%) entry with a live '± Nms' readout derived from the interval."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Jitter (%)", font=("Segoe UI", 11),
                     text_color=("#6b7a92", "#9dadc2")).pack(side="left")
        ms = ctk.CTkLabel(row, text="±0ms", font=("Cascadia Mono", 11),
                          text_color=("#8a97ab", "#7c8aa3"))
        ms.pack(side="right")
        e = ctk.CTkEntry(row, width=56, justify="right", font=("Cascadia Mono", 12))
        e.insert(0, "10")
        e.pack(side="right", padx=(0, 10))
        e.bind("<KeyRelease>", lambda _ev: self._on_change())
        setattr(self, attr, e)
        setattr(self, ms_attr, ms)

    # ---------- settings <-> ui ----------
    def _apply_settings_to_ui(self):
        s = self.s
        self.m_button.set(s["m_button"])
        self.m_click.set("Double" if s["m_double"] else "Single")
        self._set_entry(self.m_cps_e, self._cps_str(s["m_interval"]))
        self._set_entry(self.m_jitter_e, s["m_jitter"])
        self.m_hotkey_btn.configure(text=key_label(self.mouse_hotkey).upper())

        self.k_key_e.delete(0, "end"); self.k_key_e.insert(0, s["k_key"])
        self.k_mode.set("Hold" if s["k_hold"] else "Tap")
        self.k_unit.set(s.get("k_unit", "ms"))
        self._set_entry(self.k_every_e, self._fmt_value(s["k_interval"], s.get("k_unit", "ms")))
        self._set_entry(self.k_jitter_e, s["k_jitter"])
        self.k_hotkey_btn.configure(text=key_label(self.key_hotkey).upper())
        self._on_mode_change()

        self.appearance.set(s["appearance"])
        self._paint_swatch_selection()

    @staticmethod
    def _set_entry(entry, val):
        entry.delete(0, "end")
        entry.insert(0, str(val))

    @staticmethod
    def _cps_str(ms):
        try:
            return f"{1000.0 / float(ms):.2f}"
        except Exception:
            return "0"

    @staticmethod
    def _fmt_value(ms, unit):
        return f"{float(ms) / UNITS[unit]:g}"

    @staticmethod
    def _period_str(ms):
        """Friendly interval readout: 200ms, 1.5s, 20s, 3m."""
        ms = float(ms)
        if ms >= 60000:
            return f"{ms / 60000:g}m"
        if ms >= 1000:
            return f"{ms / 1000:g}s"
        return f"{int(round(ms))}ms"

    def _read_int(self, entry, default):
        try:
            return max(1, int(float(entry.get())))
        except Exception:
            return default

    def _read_float(self, entry, default):
        try:
            return max(0.0, float(entry.get()))
        except Exception:
            return default

    def _on_change(self, *_):
        s = self.s
        s["m_button"] = self.m_button.get()
        s["m_double"] = self.m_click.get() == "Double"
        cps = self._read_float(self.m_cps_e, 6.7)
        s["m_interval"] = max(1.0, 1000.0 / cps) if cps > 0 else 1000.0
        s["m_jitter"] = self._read_float(self.m_jitter_e, 10)
        s["k_key"] = self.k_key_e.get() or "space"
        s["k_hold"] = self.k_mode.get() == "Hold"
        unit = self.k_unit.get()
        s["k_unit"] = unit
        s["k_interval"] = max(1, int(round(self._read_float(self.k_every_e, 200) * UNITS[unit])))
        s["k_jitter"] = self._read_float(self.k_jitter_e, 10)

        self.mouse_engine.interval = s["m_interval"] / 1000.0
        self.mouse_engine.jitter = s["m_jitter"] / 100.0
        self.key_engine.interval = s["k_interval"] / 1000.0
        self.key_engine.jitter = s["k_jitter"] / 100.0
        self._refresh_cps()
        save_settings(s)

    def _on_mode_change(self):
        """Tap uses the rate; Hold ignores it, so grey the rate out in Hold."""
        state = "disabled" if self.k_mode.get() == "Hold" else "normal"
        self.k_every_e.configure(state=state)
        self.k_unit.configure(state=state)
        self._on_change()

    def _refresh_cps(self):
        self.m_cps_lbl.configure(text=self._cps_str(self.s["m_interval"]))
        self.k_cps_lbl.configure(
            text="HOLD" if self.s["k_hold"] else self._period_str(self.s["k_interval"]))
        self._refresh_jitter()

    def _refresh_jitter(self):
        m_ms = round(self.s["m_interval"] * self.s["m_jitter"] / 100.0)
        self.m_jitter_ms.configure(text=f"±{m_ms}ms")
        k_ms = round(self.s["k_interval"] * self.s["k_jitter"] / 100.0)
        self.k_jitter_ms.configure(text=f"±{k_ms}ms")

    def apply_droid_tycoon_preset(self):
        """Use the measured Droid Tycoon scrap-table/crafting swing rate."""
        self.m_button.set("Left")
        self.m_click.set("Single")
        self._set_entry(self.m_cps_e, "2.86")   # ~350ms per scrap/crafting swing
        self._set_entry(self.m_jitter_e, 10)
        self._on_change()

    # ---------- appearance / accent ----------
    def _on_appearance(self, mode):
        ctk.set_appearance_mode(mode)
        self.s["appearance"] = mode
        self.after(30, self._paint_header)
        save_settings(self.s)

    def _set_accent(self, name):
        self.accent = ACCENTS[name]
        self.accent2 = derive_shade(self.accent)
        acc, dk = self.accent, darken(self.accent)
        acc2, dk2 = self.accent2, darken(self.accent2)
        self.s["accent"] = name
        # CPS readouts + hotkey pills (mouse = accent, keyboard = sibling shade)
        self.m_cps_lbl.configure(text_color=acc)
        self.k_cps_lbl.configure(text_color=acc2)
        self.m_hotkey_btn.configure(text_color=acc)
        self.k_hotkey_btn.configure(text_color=acc2)
        # segmented selectors + mouse-button menu
        self.m_click.configure(selected_color=acc, selected_hover_color=dk)
        self.k_mode.configure(selected_color=acc2, selected_hover_color=dk2)
        self.m_button.configure(fg_color=acc, button_color=dk,
                                button_hover_color=darken(acc, 0.7))
        self.k_unit.configure(fg_color=acc2, button_color=dk2,
                              button_hover_color=darken(acc2, 0.7))
        # Start buttons — only if that engine isn't currently running (running = stop-coral)
        if not self.mouse_engine.running.is_set():
            self.m_start.configure(fg_color=acc, hover_color=dk)
        if not (self.key_engine.running.is_set() or self._held_key is not None):
            self.k_start.configure(fg_color=acc2, hover_color=dk2)
        # re-theme the header banner's two gradient colors
        self.banner_a, self.banner_b = BANNERS[name]
        self._paint_header()
        self._paint_swatch_selection()
        save_settings(self.s)

    def _paint_swatch_selection(self):
        for name, cv in self._swatch.items():
            c1, c2 = BANNERS[name]
            sel = name == self.s["accent"]
            cv.delete("all")
            cv.create_rectangle(0, 0, 22, 22, fill=c1, outline="")
            cv.create_polygon(22, 0, 22, 22, 0, 22, fill=c2, outline="")  # diagonal split
            cv.create_rectangle(2, 2, 20, 20, outline="#ffffff" if sel else "",
                                width=2)

    # ---------- hotkeys ----------
    def _begin_capture(self, target):
        self.capture_target = target
        btn = self.m_hotkey_btn if target == "mouse" else self.k_hotkey_btn
        btn.configure(text="press…")

    def on_global_key(self, key):
        if self.capture_target:
            target, self.capture_target = self.capture_target, None
            if target == "mouse":
                self.mouse_hotkey = key
                self.s["m_hotkey"] = key_label(key)
                self.after(0, lambda: self.m_hotkey_btn.configure(
                    text=key_label(key).upper()))
            else:
                self.key_hotkey = key
                self.s["k_hotkey"] = key_label(key)
                self.after(0, lambda: self.k_hotkey_btn.configure(
                    text=key_label(key).upper()))
            save_settings(self.s)
            return
        with _inject_lock:
            if key in _injecting:
                return
        if self._match(key, self.mouse_hotkey):
            self.after(0, self.toggle_mouse)
        elif self._match(key, self.key_hotkey):
            self.after(0, self.toggle_key)

    @staticmethod
    def _match(a, b):
        if isinstance(a, Key) and isinstance(b, Key):
            return a == b
        return getattr(a, "char", None) and getattr(a, "char", None) == getattr(b, "char", None)

    # ---------- toggles ----------
    def toggle_mouse(self):
        self._on_change()
        on = self.mouse_engine.toggle()
        self._sync_mouse_running(on)

    def _sync_mouse_running(self, on=None):
        on = self.mouse_engine.running.is_set() if on is None else on
        self.m_start.configure(
            text="■  Stop" if on else "▶  Start",
            fg_color=COL_STOP if on else self.accent,
            hover_color=darken(COL_STOP) if on else darken(self.accent))
        self.m_state_lbl.configure(text="CPS\nLIVE" if on else "CPS\nIDLE",
                                   text_color=COL_GO if on else ("#6b7a92", "#9dadc2"))

    def toggle_key(self):
        self._on_change()
        if self.s["k_hold"] and self._held_key is not None:
            # currently holding -> release & stop
            self.key_engine.stop_clicking()
            self._release_held()
            self._sync_key_running(False)
            return
        on = self.key_engine.toggle()
        if not on:
            self._release_held()
        self._sync_key_running(on)

    def _sync_key_running(self, on=None):
        holding = self._held_key is not None
        on = (self.key_engine.running.is_set() or holding) if on is None else on
        self.k_start.configure(
            text="■  Stop" if on else "▶  Start",
            fg_color=COL_STOP if on else self.accent2,
            hover_color=darken(COL_STOP) if on else darken(self.accent2))
        self.k_state_lbl.configure(text="EVERY\nLIVE" if on else "EVERY\nIDLE",
                                   text_color=COL_GO if on else ("#6b7a92", "#9dadc2"))

    # ---------- shutdown ----------
    def on_close(self):
        self.mouse_engine.shutdown()
        self.key_engine.shutdown()
        self._release_held()
        try:
            self.listener.stop()
        except Exception:
            pass
        save_settings(self.s)
        timer_end()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
