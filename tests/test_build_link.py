import json
import os
import socket
import tempfile
import threading
import time
import unittest

from build_link.engine import BuildEngine, Stopped, StepError, validate_actions, MAX_HOLD_S
from build_link.server import BuildLinkServer


class FakeBackend:
    def __init__(self):
        self.events = []
        self.state = "ok"
        self.down = set()
        self.lock = threading.Lock()
        self.real = None
        self.hotkey = None
        self.fail_on = None

    def _rec(self, *e):
        with self.lock:
            self.events.append(e)

    def key_down(self, n):
        if self.fail_on == n:
            raise OSError("boom")
        self.down.add(n)
        self._rec("kd", n)

    def key_up(self, n):
        self.down.discard(n)
        self._rec("ku", n)

    def button_down(self, n):
        self.down.add("m:" + n)
        self._rec("bd", n)

    def button_up(self, n):
        self.down.discard("m:" + n)
        self._rec("bu", n)

    def mouse_move(self, dx, dy):
        self._rec("mv", dx, dy)

    def target_state(self):
        return self.state

    def start_watch(self, real, hotkey):
        self.real, self.hotkey = real, hotkey


def wait_until(fn, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return True
        time.sleep(0.005)
    return False


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.b = FakeBackend()
        self.stops = []
        self.busy = False
        self.e = BuildEngine(self.b, busy=lambda: self.busy, on_event=self.stops.append)

    def tearDown(self):
        self.e.shutdown()

    def keep_beating(self):
        alive = threading.Event()

        def go():
            while not alive.wait(0.05):
                self.e.beat()
        threading.Thread(target=go, daemon=True).start()
        return alive

    def test_refuses_to_arm_unless_minecraft_is_in_front_and_captured(self):
        self.b.state = "focus"
        self.assertEqual(self.e.arm(), "focus")
        self.b.state = "screen"
        self.assertEqual(self.e.arm(), "screen")
        self.b.state = "ok"
        self.busy = True
        self.assertEqual(self.e.arm(), "busy")
        self.busy = False
        self.assertIsNone(self.e.arm())

    def test_nothing_is_sent_while_disarmed(self):
        with self.assertRaises(Stopped):
            self.e.run([{"k": "tap", "key": "w"}])
        self.assertEqual(self.b.events, [])

    def test_runs_and_releases_bounded_holds(self):
        self.e.arm()
        self.e.run([{"k": "down", "key": "shift"}, {"k": "hold", "key": "w", "ms": 60},
                    {"k": "mouse", "dx": 100, "dy": -30}, {"k": "click", "button": "right"}])
        self.assertEqual(self.b.down, {"shift"})
        moved = [e for e in self.b.events if e[0] == "mv"]
        self.assertEqual(sum(e[1] for e in moved), 100)
        self.assertEqual(sum(e[2] for e in moved), -30)
        self.assertGreater(len(moved), 1)  # sliced at the human-paced rate
        self.e.stop()
        self.assertEqual(self.b.down, set())

    def test_hold_with_a_second_key(self):
        self.e.arm()
        self.e.run([{"k": "hold", "key": "w", "with": "space", "ms": 30}])
        self.assertEqual([e for e in self.b.events if e[0] in ("kd", "ku")],
                         [("kd", "w"), ("kd", "space"), ("ku", "space"), ("ku", "w")])
        with self.assertRaises(StepError):
            validate_actions([{"k": "hold", "key": "w", "with": "shift", "ms": 30}])

    def test_validation(self):
        for bad in ([], [{"k": "down", "key": "w"}], [{"k": "hold", "key": "q", "ms": 10}],
                    [{"k": "hold", "key": "w", "ms": 5000}], [{"k": "mouse", "dx": 99999, "dy": 0}],
                    [{"k": "click", "button": "middle"}], [{"k": "nope"}], [{"k": "mouse", "dx": 1.5, "dy": 0}]):
            with self.assertRaises(StepError):
                validate_actions(bad)

    def test_watchdog_releases_within_half_a_second(self):
        self.e.arm()
        self.e.run([{"k": "down", "key": "shift"}])
        t0 = time.monotonic()
        self.assertTrue(wait_until(lambda: not self.e.armed, 1.5))
        self.assertLess(time.monotonic() - t0, 0.65)
        self.assertEqual(self.b.down, set())
        self.assertEqual(self.stops[-1]["reason"], "watchdog")

    def test_each_stop_path_releases_everything(self):
        for reason, cause in (("focus", lambda: setattr(self.b, "state", "focus")),
                              ("screen", lambda: setattr(self.b, "state", "screen")),
                              ("input", lambda: self.b.real()),
                              ("hotkey", lambda: self.b.hotkey()),
                              ("busy", lambda: setattr(self, "busy", True))):
            self.b.state = "ok"
            self.busy = False
            self.assertIsNone(self.e.arm(), reason)
            alive = self.keep_beating()
            done = {}

            def hold():
                try:
                    self.e.run([{"k": "down", "key": "shift"}, {"k": "hold", "key": "w", "ms": 1500}])
                    done["r"] = "finished"
                except Stopped as s:
                    done["r"] = s.reason
            t = threading.Thread(target=hold)
            t.start()
            self.assertTrue(wait_until(lambda: "w" in self.b.down))
            cause()
            t.join(2)
            alive.set()
            self.assertEqual(done.get("r"), reason)
            self.assertEqual(self.b.down, set(), reason)
            self.assertEqual(self.stops[-1]["reason"], reason)
            self.assertFalse(self.e.armed)

    def test_send_error_stops_and_releases(self):
        self.e.arm()
        self.e.run([{"k": "down", "key": "shift"}])
        self.b.fail_on = "w"
        with self.assertRaises(Stopped):
            self.e.run([{"k": "hold", "key": "w", "ms": 50}])
        self.assertEqual(self.b.down, set())

    def test_click_rate_is_limited(self):
        self.e.arm()
        alive = self.keep_beating()
        t0 = time.monotonic()
        self.e.run([{"k": "click", "button": "right", "ms": 10}] * 4)
        alive.set()
        self.assertGreaterEqual(time.monotonic() - t0, 3 * 0.18 - 0.01)

    def test_hold_cap(self):
        self.assertLessEqual(MAX_HOLD_S, 2.0)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.b = FakeBackend()
        self.e = BuildEngine(self.b)
        self.dir = tempfile.mkdtemp()
        self.s = BuildLinkServer(self.e, version="test", link_file=os.path.join(self.dir, "build-link.json"))
        self.s.start()

    def tearDown(self):
        self.s.shutdown()
        self.e.shutdown()

    def connect(self, token=None):
        with open(self.s.link_file, encoding="utf-8") as fh:
            info = json.load(fh)
        c = socket.create_connection(("127.0.0.1", info["port"]), timeout=3)
        f = c.makefile("r", encoding="utf-8")
        c.sendall((json.dumps({"hello": 1, "token": token or info["token"]}) + "\n").encode())
        return c, f

    def ask(self, c, f, msg):
        c.sendall((json.dumps(msg) + "\n").encode())
        while True:
            reply = json.loads(f.readline())
            if reply.get("id") == msg.get("id"):
                return reply

    def test_wrong_token_is_refused(self):
        c, f = self.connect("nope")
        self.assertEqual(json.loads(f.readline())["reason"], "token")
        c.close()

    def test_arm_step_and_disconnect_releases(self):
        c, f = self.connect()
        self.assertEqual(json.loads(f.readline())["hello"], 1)
        self.assertTrue(self.ask(c, f, {"id": 1, "op": "arm"})["ok"])
        r = self.ask(c, f, {"id": 2, "op": "step", "do": [{"k": "down", "key": "shift"}, {"k": "tap", "key": "1"}]})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.b.down, {"shift"})
        st = self.ask(c, f, {"id": 3, "op": "status"})
        self.assertTrue(st["armed"])
        bad = self.ask(c, f, {"id": 4, "op": "step", "do": [{"k": "down", "key": "w"}]})
        self.assertEqual(bad["reason"], "step")
        self.assertEqual(self.b.down, set())  # a refused step stops the build
        self.assertTrue(self.ask(c, f, {"id": 5, "op": "arm"})["ok"])
        self.ask(c, f, {"id": 6, "op": "step", "do": [{"k": "down", "key": "shift"}]})
        c.close()
        self.assertTrue(wait_until(lambda: not self.e.armed))
        self.assertEqual(self.b.down, set())
        # The session log: connected, arms, each step with its answer, the stop, disconnected.
        self.assertTrue(wait_until(lambda: os.path.exists(self.s.log_file) and "disconnected" in open(self.s.log_file, encoding="utf-8").read()))
        with open(self.s.log_file, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        kinds = [r["type"] for r in rows]
        for k in ("connected", "arm", "step", "stopped", "disconnected"):
            self.assertIn(k, kinds)
        refused = [r for r in rows if r["type"] == "step" and not r["ok"]]
        self.assertEqual(refused[0]["reason"], "step")

    def test_stop_event_is_pushed(self):
        c, f = self.connect()
        f.readline()
        self.ask(c, f, {"id": 1, "op": "arm"})
        self.b.state = "screen"
        msg = json.loads(f.readline())
        self.assertEqual(msg, {"event": "stopped", "reason": "screen", "text": msg["text"]})
        c.close()


if __name__ == "__main__":
    unittest.main()
