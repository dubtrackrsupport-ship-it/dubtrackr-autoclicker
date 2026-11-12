"""Manual check of link-only mode (--build-link-only): no window, never the focus, ends when asked.

Not part of the unit tests (it opens a stand-in window). It opens a small stand-in window and makes
sure it is in front (it stops otherwise: nothing else is touched). Then it starts AutoClickr in
link-only mode the way the DubTrackr app does (no console window, hidden), with its own empty
settings folder (APPDATA points at a temporary folder: the real AutoClickr is never touched). For
8 s it checks, every 10 ms, that the stand-in stays in front, and every 100 ms that no top-level
window of the process is visible. Then it waits for the link file, connects, asks it to quit and
checks the process ends and the link file is gone.

    py -3.14 tests/manual_link_only_check.py
"""

import ctypes
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
u = ctypes.windll.user32
u.GetForegroundWindow.restype = wintypes.HWND
STAND_IN = "AutoClickr link-only stand-in"

STAND_IN_CODE = f"""
import tkinter as tk
r = tk.Tk(); r.title({STAND_IN!r}); r.geometry('320x120+60+60')
tk.Label(r, text='Link-only check: closes by itself').pack(expand=True)
r.after(200, lambda: (r.lift(), r.focus_force()))
r.after(30000, r.destroy)
r.mainloop()
"""


def title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def windows_of(pid):
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


def main():
    stand = subprocess.Popen([sys.executable, "-c", STAND_IN_CODE])
    try:
        stand_hwnd = None
        for _ in range(50):
            time.sleep(0.1)
            w = [h for h in windows_of(stand.pid) if title(h) == STAND_IN]
            if w and u.GetForegroundWindow() == w[0]:
                stand_hwnd = w[0]
                break
        if not stand_hwnd:
            print("SKIP: the stand-in could not become the window in front; nothing was started")
            return 2
        appdata = tempfile.mkdtemp(prefix="autoclickr-linkonly-")
        link = os.path.join(appdata, "DubtrackrAutoClicker", "build-link.json")
        si = subprocess.STARTUPINFO()
        si.dwFlags |= 0x00000001  # STARTF_USESHOWWINDOW
        si.wShowWindow = 0        # SW_HIDE
        t0 = time.time()
        app = subprocess.Popen([sys.executable, os.path.join(HERE, "dubtrackr_autoclicker.py"), "--build-link-only",
                                "--parent-pid", str(os.getpid()), "--idle-minutes", "1"],
                               cwd=HERE, env=dict(os.environ, APPDATA=appdata), creationflags=0x08000000, startupinfo=si)
        lost = None; shown = []; next_list = 0.0
        while time.time() - t0 < 8:
            time.sleep(0.01)
            now = time.time() - t0
            fg = u.GetForegroundWindow()
            if lost is None and fg != stand_hwnd:
                lost = (round(now, 3), title(fg))
            if now >= next_list:
                next_list = now + 0.1
                for h in windows_of(app.pid):
                    if u.IsWindowVisible(h):
                        shown.append((round(now, 3), title(h)))
        linked = os.path.exists(link)
        quit_ok = False
        if linked:
            with open(link, encoding="utf-8") as f:
                info = json.load(f)
            c = socket.create_connection(("127.0.0.1", info["port"]), timeout=3)
            r = c.makefile("r", encoding="utf-8")
            c.sendall((json.dumps({"hello": 1, "token": info["token"]}) + "\n").encode())
            r.readline()
            c.sendall((json.dumps({"id": 1, "op": "quit"}) + "\n").encode())
            quit_ok = bool(json.loads(r.readline()).get("ok"))
            r.close(); c.close()
        try:
            app.wait(5)
            ended = True
        except subprocess.TimeoutExpired:
            app.kill(); ended = False
        print(f"focus left the stand-in: {lost or 'never'}")
        print(f"visible windows of the link-only process: {shown[:5] or 'none'}")
        print(f"link file written: {linked}; quit answered: {quit_ok}; process ended: {ended}; link file gone: {not os.path.exists(link)}")
        ok = lost is None and not shown and linked and quit_ok and ended and not os.path.exists(link)
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        stand.kill()


if __name__ == "__main__":
    sys.exit(main())
