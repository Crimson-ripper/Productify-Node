"""Unit tests for System Tray icon generation and logic."""

import unittest
from productify_node.tray import make_tray_icon, NodeSystemTray
from PIL import Image


class TestSystemTray(unittest.TestCase):

    def test_make_tray_icon(self):
        img = make_tray_icon("#10b981", size=64)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

    def test_tray_menu_build(self):
        tray = NodeSystemTray()
        menu = tray._build_menu()
        self.assertIsNotNone(menu)
        # Should have menu items
        items = list(menu.items)
        self.assertGreater(len(items), 3)

    def test_get_current_image(self):
        tray = NodeSystemTray()
        img = tray._get_current_image()
        self.assertIsInstance(img, Image.Image)


if __name__ == "__main__":
    unittest.main()
