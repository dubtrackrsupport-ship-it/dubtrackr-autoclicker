"""The local channel the DubTrackr app talks to: one TCP connection on 127.0.0.1, JSON lines.

The port and a random token are written to %APPDATA%\\DubtrackrAutoClicker\\build-link.json when
AutoClickr starts; a client must send the token first. Only one client at a time.

Client to engine:
  {"hello": 1, "token": "..."}                       -> {"hello": 1, "engine": "...", "version": "..."}
  {"id": 1, "op": "arm", "rate": "normal" | "fast", "hold": "vk:17"}   (hold: the sneak key)  -> {"id": 1, "ok": true} | {"id": 1, "ok": false, "reason", "text"}
  {"op": "beat"}                                     (no answer; at least every 500 ms while armed)
  {"id": 2, "op": "step", "do": [actions]}           -> {"id": 2, "ok": true, "ms": 312} | ok false with reason
  {"id": 3, "op": "stop"}                            -> {"id": 3, "ok": true}
  {"id": 4, "op": "status"}                          -> {"id": 4, "ok": true, "armed", "held", "reason", "target"}
Engine to client, any time: {"event": "stopped", "reason", "text"}
"""

import json
import os
import queue
import secrets
import socket
import threading
import time

from .engine import STOP_REASONS, Stopped, StepError

PROTOCOL = 1
MAX_LINE = 64 * 1024
LOG_MAX = 5 * 1024 * 1024


def link_file_path():
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DubtrackrAutoClicker")
    return os.path.join(base, "build-link.json")


class BuildLinkServer(threading.Thread):
    def __init__(self, engine, version="dev", port=0, link_file=None, token=None):
        super().__init__(daemon=True, name="build-link-server")
        self.engine = engine
        self.version = version
        self.token = token or secrets.token_hex(16)
        self.link_file = link_file if link_file is not None else link_file_path()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", port))
        self._sock.listen(1)
        self._sock.settimeout(0.2)
        self.port = self._sock.getsockname()[1]
        self._alive = True
        self._client = None
        self._send_lock = threading.Lock()
        # The engine's own log of the newest session (build-link.log beside the link file): every
        # step with its actions, the answer, how long it took and where input would go before and
        # after, and every stop. Started fresh for each connection, at most LOG_MAX bytes.
        self.log_file = os.path.join(os.path.dirname(self.link_file), "build-link.log") if self.link_file else None
        self._log = None
        self._log_lock = threading.Lock()
        self._t0 = time.monotonic()
        engine._on_event = self._event
        if self.link_file:
            try:
                os.makedirs(os.path.dirname(self.link_file), exist_ok=True)
                with open(self.link_file, "w", encoding="utf-8") as f:
                    json.dump({"protocol": PROTOCOL, "port": self.port, "token": self.token,
                               "version": version, "pid": os.getpid()}, f)
            except OSError:
                pass

    def _event(self, event):
        self.trace({"type": "stopped", **event})
        self._write(self._client, event)

    def trace(self, entry):
        with self._log_lock:
            if self._log is None:
                return
            try:
                if self._log.tell() < LOG_MAX:
                    self._log.write(json.dumps({"t": round((time.monotonic() - self._t0) * 1000), **entry}) + chr(10))
                    self._log.flush()
            except (OSError, ValueError):
                pass

    def _open_log(self):
        with self._log_lock:
            if self._log is not None or not self.log_file:
                return
            try:
                self._log = open(self.log_file, "w", encoding="utf-8")
                self._t0 = time.monotonic()
            except OSError:
                self._log = None

    def _close_log(self):
        with self._log_lock:
            if self._log is not None:
                try:
                    self._log.close()
                except OSError:
                    pass
                self._log = None

    def _write(self, conn, msg):
        if conn is None:
            return
        data = (json.dumps(msg) + "\n").encode("utf-8")
        with self._send_lock:
            try:
                conn.sendall(data)
            except OSError:
                pass

    def run(self):
        while self._alive:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if self._client is not None:
                self._write(conn, {"ok": False, "reason": "busy", "text": "Another app is already connected."})
                conn.close()
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        conn.settimeout(None)
        steps = queue.Queue()
        worker = threading.Thread(target=self._steps, args=(conn, steps), daemon=True)
        authed = False
        buf = b""
        try:
            while self._alive:
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_LINE and b"\n" not in buf:
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(msg, dict):
                        continue
                    if not authed:
                        if msg.get("hello") == PROTOCOL and secrets.compare_digest(str(msg.get("token", "")), self.token):
                            authed = True
                            self._client = conn
                            self._open_log()
                            self.trace({"type": "connected", "version": self.version})
                            worker.start()
                            self._write(conn, {"hello": PROTOCOL, "engine": "autoclickr-build-link", "version": self.version})
                            continue
                        self._write(conn, {"ok": False, "reason": "token", "text": "Wrong link token."})
                        return
                    self._handle(conn, msg, steps)
        finally:
            if self._client is conn:
                self._client = None
                self.engine.stop("disconnect")
                self.trace({"type": "disconnected"})
                self._close_log()
            steps.put(None)
            try:
                conn.close()
            except OSError:
                pass

    def _handle(self, conn, msg, steps):
        op = msg.get("op")
        mid = msg.get("id")
        if op == "beat":
            self.engine.beat()
        elif op == "arm":
            why = self.engine.arm(msg.get("rate", "normal"), msg.get("hold", "shift"))
            self.trace({"type": "arm", "ok": why is None, "reason": why})
            self._write(conn, {"id": mid, "ok": why is None} if why is None else
                        {"id": mid, "ok": False, "reason": why, "text": STOP_REASONS.get(why, why)})
        elif op == "stop":
            self.engine.stop("brain")
            self._write(conn, {"id": mid, "ok": True})
        elif op == "status":
            try:
                target = self.engine._b.target_state()
            except Exception:
                target = "focus"
            self._write(conn, {"id": mid, "ok": True, "armed": self.engine.armed, "held": self.engine.held(),
                               "reason": self.engine.reason, "target": target})
        elif op == "step":
            self.engine.beat()
            steps.put((mid, msg.get("do")))
        else:
            self._write(conn, {"id": mid, "ok": False, "reason": "op", "text": "Unknown request."})

    def _steps(self, conn, steps):
        while True:
            item = steps.get()
            if item is None:
                return
            mid, actions = item
            started = time.monotonic()
            before = self._input_target()
            try:
                if not self.engine.armed:
                    raise Stopped(self.engine.reason or "brain")
                self.engine.run(actions)
                ms = round((time.monotonic() - started) * 1000)
                self._write(conn, {"id": mid, "ok": True, "ms": ms})
                self.trace({"type": "step", "id": mid, "do": actions, "ok": True, "ms": ms, "before": before, "after": self._input_target()})
            except Stopped as s:
                self._write(conn, {"id": mid, "ok": False, "reason": s.reason, "text": STOP_REASONS.get(s.reason, s.reason)})
                self.trace({"type": "step", "id": mid, "do": actions, "ok": False, "reason": s.reason, "before": before, "after": self._input_target()})
            except StepError as e:
                self.engine.stop("brain")
                self._write(conn, {"id": mid, "ok": False, "reason": "step", "text": str(e)})
                self.trace({"type": "step", "id": mid, "do": actions, "ok": False, "reason": "step", "text": str(e)})

    def _input_target(self):
        try:
            return self.engine._b.target_state()
        except Exception:
            return "focus"

    def shutdown(self):
        self._alive = False
        self.engine.stop("shutdown")
        try:
            self._sock.close()
        except OSError:
            pass
        if self._client is not None:
            try:
                self._client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self._close_log()
        if self.link_file:
            try:
                os.remove(self.link_file)
            except OSError:
                pass
