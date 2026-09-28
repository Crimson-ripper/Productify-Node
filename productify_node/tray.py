"""Industry-Standard System Tray Daemon for Productify Node.

Provides background taskbar presence with live status indication, quick toggle
controls, Emergency Stop triggers, and seamless minimize-to-tray capability.
"""

import sys
import threading
import logging
import webbrowser
from PIL import Image, ImageDraw
import pystray
from productify_node.state import node_state
from productify_node.container import container_mgr
from productify_node.thermal_guard import thermal_guard

logger = logging.getLogger("productify_node.tray")


def make_tray_icon(color_hex="#10b981", size=64):
    """Draw a crisp high-DPI circular status icon."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Background circle
    draw.ellipse([2, 2, size - 3, size - 3], fill="#11141a", outline="#2e3846", width=4)
    # Inner colored badge
    draw.ellipse([16, 16, size - 17, size - 17], fill=color_hex)
    return image


class NodeSystemTray:
    """Manages the OS system tray icon, background menu, and window visibility."""

    def __init__(self):
        self.icon = None
        self._thread = None
        self._show_window_cb = None
        self._exit_cb = None

        self._icons = {
            "LIVE": make_tray_icon("#10b981"),       # Emerald Green
            "PAUSED": make_tray_icon("#f59e0b"),     # Amber
            "OVERHEAT": make_tray_icon("#ef4444"),   # Crimson Red
        }

    def _get_current_image(self):
        if thermal_guard.is_overheated:
            return self._icons["OVERHEAT"]
        return self._icons["LIVE"] if node_state.is_live else self._icons["PAUSED"]

    def _get_title(self):
        st = "OVERHEATED" if thermal_guard.is_overheated else ("LIVE (Earning)" if node_state.is_live else "PAUSED")
        return f"Productify Node — {st}"

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda text: self._get_title(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🟢 Set Live (Earn)", self._action_set_live, checked=lambda item: node_state.is_live and not thermal_guard.is_overheated),
            pystray.MenuItem("⏸️ Pause Node (Safe)", self._action_set_pause, checked=lambda item: not node_state.is_live),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📊 Open Dashboard", self._action_open_dashboard, default=True),
            pystray.MenuItem("🚨 Emergency Stop & Wipe", self._action_emergency_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Exit Productify Node", self._action_exit),
        )

    def _action_set_live(self, icon, item):
        node_state.set_live()
        self.refresh()

    def _action_set_pause(self, icon, item):
        node_state.set_paused()
        self.refresh()

    def _action_open_dashboard(self, icon=None, item=None):
        if self._show_window_cb:
            try:
                self._show_window_cb()
                return
            except Exception as e:
                logger.warning(f"Error calling show_window_cb: {e}")
        webbrowser.open("http://127.0.0.1:48123/ui")

    def _action_emergency_stop(self, icon, item):
        container_mgr.destroy_all_pods()
        node_state.set_paused()
        node_state.log("🚨 Emergency Stop invoked from System Tray. All pods wiped.", level="WARNING")
        self.refresh()

    def _action_exit(self, icon=None, item=None):
        logger.info("Exiting Productify Node from System Tray...")
        if self._exit_cb:
            try:
                self._exit_cb()
            except Exception:
                pass
        self.stop()
        sys.exit(0)

    def refresh(self):
        """Update icon image and tooltip based on latest node state."""
        if self.icon:
            try:
                self.icon.icon = self._get_current_image()
                self.icon.title = self._get_title()
            except Exception as e:
                logger.debug(f"Tray refresh error: {e}")

    def start(self, show_window_cb=None, exit_cb=None):
        """Launch tray icon in background daemon thread."""
        self._show_window_cb = show_window_cb
        self._exit_cb = exit_cb

        def _run():
            self.icon = pystray.Icon(
                "ProductifyNode",
                self._get_current_image(),
                self._get_title(),
                menu=self._build_menu()
            )
            node_state.add_listener(lambda s: self.refresh())
            self.icon.run()

        self._thread = threading.Thread(target=_run, daemon=True, name="SystemTrayThread")
        self._thread.start()
        logger.info("System Tray daemon active.")

    def notify(self, title, message):
        """Send native OS desktop notification bubble."""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception as e:
                logger.debug(f"Tray notification error: {e}")

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


system_tray = NodeSystemTray()
