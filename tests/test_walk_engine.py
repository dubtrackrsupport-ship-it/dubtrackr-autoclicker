import threading
import time
import unittest

from walk_engine import WalkEngine


class WalkEngineTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.changed = threading.Condition()

        def record(action, key):
            with self.changed:
                self.events.append((action, key, time.monotonic()))
                self.changed.notify_all()

        self.engine = WalkEngine(lambda key: record("down", key),
                                 lambda key: record("up", key))
        self.engine.start()

    def tearDown(self):
        self.engine.shutdown()
        self.engine.join(1)
        self.assertFalse(self.engine.is_alive())

    def wait_for(self, count, timeout=4):
        with self.changed:
            self.assertTrue(self.changed.wait_for(lambda: len(self.events) >= count, timeout),
                            self.events)

    def test_cycle_order_duration_and_gap(self):
        self.engine.interval = 0.2
        self.engine.start_walking()
        self.wait_for(5)
        self.engine.stop_walking()
        self.assertEqual([(a, k) for a, k, _ in self.events[:5]],
                         [("down", "s"), ("up", "s"), ("down", "w"),
                          ("up", "w"), ("down", "s")])
        for start, end in ((0, 1), (2, 3)):
            self.assertAlmostEqual(self.events[end][2] - self.events[start][2], 1, delta=0.15)
        self.assertAlmostEqual(self.events[4][2] - self.events[3][2], 0.2, delta=0.15)

    def test_stop_releases_s_immediately_without_w(self):
        self.engine.start_walking()
        self.wait_for(1)
        start = time.monotonic()
        self.engine.stop_walking()
        self.assertLess(time.monotonic() - start, 0.2)
        time.sleep(0.05)
        self.assertEqual([(a, k) for a, k, _ in self.events], [("down", "s"), ("up", "s")])

    def test_stop_releases_w_immediately(self):
        self.engine.start_walking()
        self.wait_for(3)
        self.engine.stop_walking()
        self.assertEqual(self.events[-1][:2], ("up", "w"))
        self.assertFalse(self.engine.active)

    def test_stop_during_initial_delay_sends_nothing(self):
        self.engine.start_walking(delay=0.2)
        self.engine.stop_walking()
        time.sleep(0.25)
        self.assertEqual(self.events, [])

    def test_stop_during_gap_cancels_next_cycle(self):
        self.engine.interval = 0.1
        self.engine.start_walking()
        self.wait_for(4)
        self.engine.stop_walking()
        time.sleep(0.2)
        self.assertEqual(len(self.events), 4)

    def test_rapid_stop_restart_never_overlaps_keys(self):
        for index in range(12):
            self.engine.start_walking()
            self.wait_for(index * 2 + 1)
            self.engine.stop_walking()
        self.assertEqual([(a, k) for a, k, _ in self.events],
                         [("down", "s"), ("up", "s")] * 12)

    def test_shutdown_releases_key_and_exits(self):
        self.engine.start_walking()
        self.wait_for(1)
        self.engine.shutdown()
        self.engine.join(1)
        self.assertEqual(self.events[-1][:2], ("up", "s"))
        self.assertFalse(self.engine.is_alive())

    def test_invalid_intervals_are_rejected(self):
        for value in (0, -1, 0.09, 86401, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.engine.interval = value
        for value in (0.1, 30, 86400):
            self.engine.interval = value
            self.assertEqual(self.engine.interval, value)

    def test_press_failure_attempts_release_and_stops(self):
        def fail(key):
            raise OSError("test input failure")

        self.engine._press = fail
        self.engine.start_walking()
        self.wait_for(1)
        self.assertEqual(self.events[0][:2], ("up", "s"))
        self.assertFalse(self.engine.active)
        self.assertEqual(self.engine.error, "test input failure")

    def test_release_failure_stops_before_forward_and_can_retry(self):
        original_release = self.engine._release
        self.engine._release = lambda key: (_ for _ in ()).throw(OSError("release failed"))
        self.engine.start_walking()
        self.wait_for(1)
        self.engine.stop_walking()
        self.assertFalse(self.engine.active)
        self.assertEqual(self.engine.error, "release failed")
        self.assertEqual(len(self.events), 1)
        self.engine._release = original_release
        self.engine.stop_walking()
        self.assertEqual(self.events[-1][:2], ("up", "s"))


if __name__ == "__main__":
    unittest.main()
