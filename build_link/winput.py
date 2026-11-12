"""Windows input for the build link: SendInput with scan codes and relative mouse moves, the
foreground check, the cursor check, and the player's own input seen through low-level hooks.

Games read keys by scan code and the mouse as relative motion, so both are sent that way. Our own
events carry Windows' "injected" flag; the hooks use it to tell the player's input from ours.
Nothing here hides that flag or disguises the input.
"""

import ctypes
import os
import sys
from ctypes import wintypes

TARGETS = ("minecraft.windows.exe",)
STOP_KEY_VK = 0x78  # F9

SCAN = {
    "w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "space": 0x39, "shift": 0x2A,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A,
}
BUTTON_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0001, 0x0002, 0x0008
MOUSEEVENTF_MOVE = 0x0001
CURSOR_SHOWING = 0x00000001
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
WM_KEYDOWN, WM_SYSKEYDOWN, WM_MOUSEMOVE = 0x0100, 0x0104, 0x0200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hCursor", wintypes.HANDLE), ("ptScreenPos", wintypes.POINT)]


class WindowsBackend:
    """The real backend. Only usable on Windows."""

    def __init__(self, targets=TARGETS):
        if sys.platform != "win32":
            raise OSError("The build link needs Windows.")
        self._u = ctypes.WinDLL("user32", use_last_error=True)
        self._k = ctypes.WinDLL("kernel32", use_last_error=True)
        self._u.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._u.GetForegroundWindow.restype = wintypes.HWND
        self._u.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self._k.OpenProcess.restype = wintypes.HANDLE
        self._k.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        self._targets = tuple(t.lower() for t in targets)
        self._listeners = []
        self._pid_cache = (None, None)

    # ----- sending -----
    def _send(self, inp):
        if self._u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
            raise OSError("SendInput failed (%d)" % ctypes.get_last_error())

    def _scan(self, name):
        """(scan code, extended) for a key name or "vk:<n>", through the active keyboard layout."""
        if name in SCAN:
            return SCAN[name], False
        vk = int(name[3:])
        # MAPVK_VK_TO_VSC_EX gives 0xE0xx for extended keys (right Ctrl, arrows).
        sc = self._u.MapVirtualKeyW(vk, 4)
        if not sc:
            raise OSError("no scan code for virtual key %d" % vk)
        return sc & 0xFF, bool(sc & 0xFF00)

    def _key(self, name, up):
        sc, ext = self._scan(name)
        inp = INPUT(type=INPUT_KEYBOARD)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if ext else 0)
        inp.u.ki = KEYBDINPUT(0, sc, flags, 0, 0)
        self._send(inp)

    def key_down(self, name):
        self._key(name, False)

    def key_up(self, name):
        self._key(name, True)

    def _button(self, name, up):
        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(0, 0, 0, BUTTON_FLAGS[name][1 if up else 0], 0, 0)
        self._send(inp)

    def button_down(self, name):
        self._button(name, False)

    def button_up(self, name):
        self._button(name, True)

    def mouse_move(self, dx, dy):
        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(int(dx), int(dy), 0, MOUSEEVENTF_MOVE, 0, 0)
        self._send(inp)

    # ----- where input would go -----
    def _exe_of_window(self, hwnd):
        pid = wintypes.DWORD()
        self._u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        cached_pid, cached = self._pid_cache
        if cached_pid == pid.value:
            return cached
        h = self._k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if not self._k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return ""
            exe = os.path.basename(buf.value).lower()
        finally:
            self._k.CloseHandle(h)
        self._pid_cache = (pid.value, exe)
        return exe

    def target_state(self):
        """'ok' when Minecraft is in front with the mouse captured, else 'focus' or 'screen'."""
        hwnd = self._u.GetForegroundWindow()
        if not hwnd or self._exe_of_window(hwnd) not in self._targets:
            return "focus"
        info = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
        if not self._u.GetCursorInfo(ctypes.byref(info)):
            return "screen"
        # In play the game hides the cursor. Chat, the pause menu, the inventory and every other
        # screen show it.
        return "screen" if info.flags & CURSOR_SHOWING else "ok"

    # ----- the player's own input -----
    def start_watch(self, on_real_input, on_hotkey):
        from pynput import keyboard, mouse

        def kfilter(msg, data):
            if not data.flags & LLKHF_INJECTED and msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                (on_hotkey if data.vkCode == STOP_KEY_VK else on_real_input)()
            return True

        moved = {"last": None}

        def mfilter(msg, data):
            if data.flags & LLMHF_INJECTED:
                return True
            if msg == WM_MOUSEMOVE:
                last = moved["last"]
                moved["last"] = (data.pt.x, data.pt.y)
                if last is not None and abs(data.pt.x - last[0]) + abs(data.pt.y - last[1]) > 2:
                    on_real_input()
            else:
                on_real_input()
            return True

        k = keyboard.Listener(win32_event_filter=kfilter)
        m = mouse.Listener(win32_event_filter=mfilter)
        k.start()
        m.start()
        self._listeners = [k, m]

    def stop_watch(self):
        for listener in self._listeners:
            try:
                listener.stop()
            except Exception:
                pass
        self._listeners = []
