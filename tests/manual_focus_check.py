"""Manual check that AutoClickr, started while a game is in front, never takes the focus, with a trace
of what does take it.

Not part of the unit tests (it opens windows). It opens a small stand-in window, makes sure the
stand-in is the window in front (it stops otherwise: nothing else is touched), then starts
AutoClickr with the stand-in counted as a game (AUTOCLICKR_QUIET_START_EXES) and its own empty
settings folder (APPDATA points at a temporary folder, so the real AutoClickr's link file and
settings are never touched). For 8 s it records, every 10 ms, which window is in front; at each
change: the window's class, title, owner, parent, styles, process and thread; every 100 ms, each
top-level window of AutoClickr's process (only when the list changes). AutoClickr writes its own
startup steps with their times (AUTOCLICKR_FOCUS_TRACE). Then it closes both and prints one merged
timeline. It runs three launch styles in turn:
  A  python.exe, no console window (as before)
  B  python.exe, no console window, STARTUPINFO "show minimized, not active"
  C  pythonw.exe (no console at all), STARTUPINFO "show minimized, not active"

    py -3.14 tests/manual_focus_check.py
"""

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
u = ctypes.windll.user32
k = ctypes.windll.kernel32
for fn in ("GetForegroundWindow", "GetParent", "GetWindow", "GetAncestor"):
    getattr(u, fn).restype = wintypes.HWND
GWL_STYLE, GWL_EXSTYLE = -16, -20
GetLong = getattr(u, "GetWindowLongPtrW", u.GetWindowLongW)
GetLong.restype = ctypes.c_ssize_t
STAND_IN = "AutoClickr focus stand-in"
APP_TITLE = "DubTrackr AutoClickr"

STAND_IN_CODE = f"""
import tkinter as tk
r = tk.Tk(); r.title({STAND_IN!r}); r.geometry('320x120+60+60')
tk.Label(r, text='Focus check: closes by itself').pack(expand=True)
r.after(200, lambda: (r.lift(), r.focus_force()))
r.after(60000, r.destroy)
r.mainloop()
"""


def text(hwnd, fn):
    buf = ctypes.create_unicode_buffer(256)
    fn(hwnd, buf, 256)
    return buf.value


def info(hwnd):
    if not hwnd:
        return "none"
    pid = wintypes.DWORD()
    tid = u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return (f"hwnd {hwnd:#x} class {text(hwnd, u.GetClassNameW)!r} title {text(hwnd, u.GetWindowTextW)!r} "
            f"pid {pid.value} tid {tid} owner {u.GetWindow(hwnd, 4) or 0:#x} parent {u.GetParent(hwnd) or 0:#x} "
            f"style {GetLong(hwnd, GWL_STYLE) & 0xffffffff:#010x} exstyle {GetLong(hwnd, GWL_EXSTYLE) & 0xffffffff:#010x} "
            f"visible {bool(u.IsWindowVisible(hwnd))} minimized {bool(u.IsIconic(hwnd))}")


def top_windows(pid):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            out.append(hwnd)
        return True

    u.EnumWindows(each, 0)
    return out


def windows_titled(title, pid):
    return [h for h in top_windows(pid) if text(h, u.GetWindowTextW) == title]


def run(label, exe, startupinfo):
    stand = subprocess.Popen([sys.executable, "-c", STAND_IN_CODE])
    events = []
    try:
        stand_hwnd = None
        for _ in range(50):
            time.sleep(0.1)
            w = windows_titled(STAND_IN, stand.pid)
            if w and u.GetForegroundWindow() == w[0]:
                stand_hwnd = w[0]
                break
        if not stand_hwnd:
            print(f"[{label}] SKIP: the stand-in could not become the window in front; nothing was started")
            return None
        trace = os.path.join(tempfile.mkdtemp(prefix="autoclickr-focus-"), "trace.txt")
        env = dict(os.environ, APPDATA=os.path.dirname(trace), AUTOCLICKR_FOCUS_TRACE=trace,
                   AUTOCLICKR_QUIET_START_EXES=os.path.basename(sys.executable))
        t0 = time.time()
        app = subprocess.Popen([exe, os.path.join(HERE, "dubtrackr_autoclicker.py")], cwd=HERE, env=env,
                               creationflags=0x08000000, startupinfo=startupinfo)  # CREATE_NO_WINDOW
        events.append((0.0, f"launched pid {app.pid} ({label})"))
        try:
            last_fg = stand_hwnd
            last_list = None
            next_list = 0.0
            lost = None
            while time.time() - t0 < 8:
                time.sleep(0.01)
                now = time.time() - t0
                fg = u.GetForegroundWindow()
                if fg != last_fg:
                    events.append((now, "FOREGROUND -> " + info(fg)))
                    if lost is None and fg != stand_hwnd:
                        lost = now
                    last_fg = fg
                if now >= next_list:
                    next_list = now + 0.1
                    lst = [info(h) for h in top_windows(app.pid)]
                    if lst != last_list:
                        events.append((now, "process windows:\n      " + ("\n      ".join(lst) if lst else "(none)")))
                        last_list = lst
            try:
                with open(trace, encoding="utf-8") as f:
                    for line in f:
                        t, step, fg = line.rstrip("\n").split(" | ")
                        events.append((float(t) - t0, f"autoclickr: {step} (in front {int(fg):#x})"))
            except OSError:
                events.append((0.0, "autoclickr wrote no trace"))
            app_hwnd = (windows_titled(APP_TITLE, app.pid) or [None])[0]
            fg = u.GetForegroundWindow()
            ok = bool(app_hwnd) and fg == stand_hwnd and lost is None
            events.sort(key=lambda e: e[0])
            print(f"\n[{label}] {'PASS' if ok else 'FAIL'}: stand-in in front after 8 s {fg == stand_hwnd}, focus left it at {lost if lost is not None else 'never'}")
            print(f"  stand-in: {info(stand_hwnd)}")
            print(f"  AutoClickr titled window: {info(app_hwnd)}")
            for t, e in events:
                print(f"  {t:6.3f}  {e}")
            return ok
        finally:
            for h in windows_titled(APP_TITLE, app.pid):
                u.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE: AutoClickr's own close (lets go of everything)
            try:
                app.wait(5)
            except subprocess.TimeoutExpired:
                app.kill()
    finally:
        stand.kill()
        time.sleep(0.5)


def main():
    quiet = subprocess.STARTUPINFO()
    quiet.dwFlags |= 0x00000001  # STARTF_USESHOWWINDOW
    quiet.wShowWindow = 7  # SW_SHOWMINNOACTIVE
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    results = {
        "A python.exe": run("A python.exe", sys.executable, None),
        "B python.exe + SW_SHOWMINNOACTIVE": run("B python.exe + SW_SHOWMINNOACTIVE", sys.executable, quiet),
        "C pythonw.exe + SW_SHOWMINNOACTIVE": run("C pythonw.exe + SW_SHOWMINNOACTIVE", pyw, quiet),
    }
    print("\nSUMMARY " + "; ".join(f"{k}: {'PASS' if v else 'SKIP' if v is None else 'FAIL'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
