"""Link-only mode: the build link with no window at all, for the DubTrackr app to start on its own.

    DubtrackrAutoClicker.exe --build-link-only [--parent-pid N] [--idle-minutes M]
    python dubtrackr_autoclicker.py --build-link-only ...

Runs the build-link engine (with its watch on the player's own keys and mouse, and F9 to stop) and
writes the same link file as AutoClickr with its window. Never imports tkinter, so no window can
appear or take the focus. Exits when the app asks ({"op": "quit"}), when the app's process is gone,
or after --idle-minutes (default 5) with no app connected; on the way out automation is off and every
key and button is let go.

A normal AutoClickr already offering the link is left alone: nothing is started.
"""

import argparse
import ctypes
import json
import os
import socket
import sys
import time

from .server import BuildLinkServer, link_file_path


def pid_alive(pid):
    """Whether process `pid` is still running (Windows; elsewhere assumed alive)."""
    if not pid or sys.platform != "win32":
        return True
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def link_offered(path=None):
    """Whether another AutoClickr already offers the link (its file names a live process and port)."""
    path = path or link_file_path()
    try:
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(info, dict) or info.get("pid") == os.getpid() or not pid_alive(info.get("pid")):
        return False
    try:
        with socket.create_connection(("127.0.0.1", int(info.get("port", 0))), timeout=0.5):
            return True
    except (OSError, ValueError):
        return False


def run(server, parent_pid=None, idle_s=300.0, clock=time.monotonic, sleep=time.sleep, alive=pid_alive):
    """Serves until asked to quit, the parent is gone, or nobody connects for idle_s. Returns why."""
    server.start()
    quiet_since = clock()
    try:
        while True:
            sleep(0.25)
            if server.quit_requested:
                return "asked"
            if parent_pid and not alive(parent_pid):
                return "parent-gone"
            if server.connected:
                quiet_since = clock()
            elif clock() - quiet_since > idle_s:
                return "idle"
    finally:
        server.shutdown()
        server.engine.shutdown()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="DubtrackrAutoClicker --build-link-only")
    ap.add_argument("--build-link-only", action="store_true")
    ap.add_argument("--parent-pid", type=int, default=0)
    ap.add_argument("--idle-minutes", type=float, default=5.0)
    args, _ = ap.parse_known_args(argv)
    if link_offered():
        return 0
    from version import VERSION
    from .engine import BuildEngine
    from .winput import WindowsBackend
    engine = BuildEngine(WindowsBackend())
    server = BuildLinkServer(engine, version=f"{VERSION} link-only")
    run(server, parent_pid=args.parent_pid, idle_s=max(10.0, args.idle_minutes * 60))
    return 0
