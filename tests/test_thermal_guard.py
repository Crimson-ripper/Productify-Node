"""Unit tests for Hardware Thermal Protection Guard."""

import unittest
from unittest.mock import patch
from productify_node.thermal_guard import ThermalGuard
from productify_node.state import node_state


class TestThermalGuard(unittest.TestCase):

    def setUp(self):
        self.guard = ThermalGuard(max_temp_c=75, warning_temp_c=70, cooldown_target_c=62, interval=1)
        node_state.set_live()

    def test_default_state(self):
        st = self.guard.get_status()
        self.assertEqual(st["max_temp_c"], 75)
        self.assertEqual(st["warning_temp_c"], 70)
        self.assertEqual(st["cooldown_target_c"], 62)
        self.assertFalse(st["is_overheated"])
        self.assertEqual(st["status"], "NORMAL")

    def test_set_limits(self):
        self.guard.set_limits(max_temp=80, warning_temp=74, cooldown_temp=65)
        st = self.guard.get_status()
        self.assertEqual(st["max_temp_c"], 80)
        self.assertEqual(st["warning_temp_c"], 74)
        self.assertEqual(st["cooldown_target_c"], 65)

    @patch("productify_node.thermal_guard.probe_gpu")
    def test_normal_temperature(self, mock_probe):
        mock_probe.return_value = {
            "available": True,
            "name": "NVIDIA Test GPU",
            "temperature_c": 52,
        }
        st = self.guard.check_once()
        self.assertEqual(st["status"], "NORMAL")
        self.assertFalse(st["is_overheated"])
        self.assertTrue(node_state.is_live)

    @patch("productify_node.thermal_guard.probe_gpu")
    def test_warning_temperature(self, mock_probe):
        mock_probe.return_value = {
            "available": True,
            "name": "NVIDIA Test GPU",
            "temperature_c": 72,
        }
        st = self.guard.check_once()
        self.assertEqual(st["status"], "WARNING")
        self.assertFalse(st["is_overheated"])

    @patch("productify_node.thermal_guard.probe_gpu")
    def test_critical_overheat_auto_pauses_node(self, mock_probe):
        mock_probe.return_value = {
            "available": True,
            "name": "NVIDIA Test GPU",
            "temperature_c": 82,
        }
        st = self.guard.check_once()
        self.assertEqual(st["status"], "CRITICAL_PAUSED")
        self.assertTrue(st["is_overheated"])
        self.assertEqual(st["overheat_events"], 1)
        # Verify node was auto-paused for hardware safety
        self.assertTrue(node_state.is_paused)

    @patch("productify_node.thermal_guard.probe_gpu")
    def test_cooldown_recovery(self, mock_probe):
        # Trigger overheat first
        mock_probe.return_value = {"available": True, "name": "NVIDIA Test GPU", "temperature_c": 80}
        self.guard.check_once()
        self.assertTrue(self.guard.is_overheated)

        # Still cooling down (66°C > 62°C target)
        mock_probe.return_value = {"available": True, "name": "NVIDIA Test GPU", "temperature_c": 66}
        st = self.guard.check_once()
        self.assertEqual(st["status"], "COOLDOWN")
        self.assertTrue(st["is_overheated"])

        # Fully cooled down (58°C <= 62°C)
        mock_probe.return_value = {"available": True, "name": "NVIDIA Test GPU", "temperature_c": 58}
        st = self.guard.check_once()
        self.assertEqual(st["status"], "NORMAL")
        self.assertFalse(st["is_overheated"])


if __name__ == "__main__":
    unittest.main()
