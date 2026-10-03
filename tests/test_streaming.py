"""Unit tests for Sunshine streaming manager and gaming diagnostics."""

import os
import unittest
from productify_node.streaming.sunshine_mgr import sunshine_mgr, get_public_ip, CONFIG_DIR
from productify_node.streaming.diagnostics import run_diagnostics, check_vigembus, check_port_availability


class TestStreamingModule(unittest.TestCase):

    def test_sunshine_manager_init(self):
        status = sunshine_mgr.get_status()
        self.assertIn("installed", status)
        self.assertIn("running", status)
        self.assertFalse(status["running"])

    def test_config_generation(self):
        conf_path, apps_path = sunshine_mgr._generate_config("TestCyberpunk", "game.exe")
        self.assertTrue(os.path.exists(conf_path))
        self.assertTrue(os.path.exists(apps_path))

        with open(conf_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("port = 47989", content)
            self.assertIn("encoder = nvenc", content)

        with open(apps_path, "r", encoding="utf-8") as f:
            apps_content = f.read()
            self.assertIn("TestCyberpunk", apps_content)

    def test_public_ip_discovery(self):
        ip = get_public_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip) >= 7)

    def test_diagnostics_report_structure(self):
        diag = run_diagnostics()
        self.assertIn("ready_for_cloud_gaming", diag)
        self.assertIn("gpu", diag)
        self.assertIn("sunshine", diag)
        self.assertIn("vigembus_controller_driver", diag)
        self.assertIn("network", diag)

    def test_port_availability_check(self):
        # Bind checking test
        ports = check_port_availability([58912])
        self.assertIn(58912, ports)


if __name__ == "__main__":
    unittest.main()
