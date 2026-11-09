"""Real Tk controls with isolated settings and recorded input, never game input."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import dubtrackr_autoclicker as module


class AppWalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.settings_dir = patch.object(module, "SETTINGS_DIR", cls.temp.name)
        cls.settings_path = patch.object(module, "SETTINGS_PATH", str(Path(cls.temp.name) / "settings.json"))
        cls.keyboard = patch.object(module, "kbd", Mock())
        cls.mouse = patch.object(module, "mouse", Mock())
        cls.listener = patch.object(module, "KeyListener", Mock())
        for item in (cls.settings_dir, cls.settings_path, cls.keyboard, cls.mouse, cls.listener):
            item.start()
        cls.app = module.App()
        cls.app.title("DubTrackr AutoClickr - Walk QA (no input)")
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.on_close()
        for item in (cls.listener, cls.mouse, cls.keyboard, cls.settings_path, cls.settings_dir):
            item.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.app.walk_engine.stop_walking()
        self.app.key_engine.stop_clicking()
        self.app._release_held()
        self.app._keys_down.clear()
        self.app.capture_target = None
        self.app.walk_engine.error = None
        self.app._set_entry(self.app.k_key_e, "space")
        self.app._set_entry(self.app.w_every_e, "30")
        self.app.w_unit.set("sec")
        self.app._on_change()

    def test_settings_round_trip(self):
        self.app._set_entry(self.app.w_every_e, "2.5")
        self.app.w_unit.set("min")
        self.assertTrue(self.app._on_walk_change())
        self.assertEqual(self.app.walk_engine.interval, 150)
        saved = module.load_settings()
        self.assertEqual(saved["w_interval"], 2.5)
        self.assertEqual(saved["w_unit"], "min")
        self.assertEqual(saved["w_hotkey"], "f8")

    def test_invalid_field_stops_walking_without_saving_invalid_value(self):
        self.app.toggle_walk()
        self.assertTrue(self.app.walk_engine.active)
        for value in ("", "nan", "inf", "-1", "0", "86401"):
            self.app._set_entry(self.app.w_every_e, value)
            self.assertFalse(self.app._on_walk_change())
            self.assertFalse(self.app.walk_engine.active)
        self.assertEqual(module.load_settings()["w_interval"], 30)

    def test_f8_repeat_does_not_toggle_again_until_release(self):
        for _ in range(4):
            self.app.on_global_key(module.Key.f8)
        self.app.update()
        self.assertTrue(self.app.walk_engine.active)
        self.app.on_global_release(module.Key.f8)
        self.app.on_global_key(module.Key.f8)
        self.app.update()
        self.assertFalse(self.app.walk_engine.active)

    def test_walking_rejects_held_movement_key(self):
        self.app._set_entry(self.app.k_key_e, "w")
        self.app._held_key = "w"
        self.app.toggle_walk()
        self.assertFalse(self.app.walk_engine.active)
        self.assertIn("Stop the keyboard", self.app.w_status.cget("text"))

    def test_keyboard_movement_is_blocked_while_walking(self):
        self.app.toggle_walk()
        self.app._set_entry(self.app.k_key_e, "s")
        self.app.toggle_key()
        self.assertTrue(self.app.walk_engine.active)
        self.assertFalse(self.app.key_engine.running.is_set())

    def test_queued_keyboard_movement_sends_no_input_while_walking(self):
        self.app.toggle_walk()
        self.app._set_entry(self.app.k_key_e, "w")
        self.app._on_change()
        module.kbd.reset_mock()
        self.app.do_key_action()
        module.kbd.press.assert_not_called()
        module.kbd.release.assert_not_called()

    def test_hotkey_collision_is_rejected(self):
        self.app._begin_capture("walk")
        self.app.on_global_key(module.Key.f6)
        self.app.update()
        self.assertEqual(self.app.walk_hotkey, module.Key.f8)
        self.assertIn("Choose a separate", self.app.w_status.cget("text"))

    def test_themes_and_layout(self):
        for name in module.ACCENTS:
            self.app._set_accent(name)
        for mode in ("Light", "Dark", "System"):
            self.app._on_appearance(mode)
            self.app.update()
        self.assertEqual(self.app.w_start.cget("text"), "Start walking")
        self.assertGreater(self.app.w_every_e.winfo_width(), 50)
        self.assertLess(self.app.w_hotkey_btn.winfo_rootx() + self.app.w_hotkey_btn.winfo_width(),
                        self.app.winfo_rootx() + self.app.winfo_width())


if __name__ == "__main__":
    unittest.main()
