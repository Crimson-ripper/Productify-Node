"""Modern Edge WebView2 Frameless Desktop Application for Productify Node.

Renders high-performance, GPU-accelerated glassmorphic desktop interface
backed by Microsoft Edge WebView2, supporting minimize-to-tray.
"""

import sys
import logging
import webview
from productify_node.bridge.local_server import local_bridge
from productify_node.tunnel import tunnel_daemon
from productify_node.thermal_guard import thermal_guard
from productify_node.tray import system_tray

logger = logging.getLogger("productify_node.webview")


class ProductifyWebViewApp:
    """Manages pywebview window lifecycle, system tray integration, and minimize-to-tray."""

    def __init__(self, port=48123):
        self.port = port
        self.window = None
        self._is_closing = False

    def show_window(self):
        """Restore and bring dashboard window to focus."""
        if self.window:
            try:
                self.window.show()
                self.window.restore()
            except Exception as e:
                logger.debug(f"Error restoring webview window: {e}")

    def hide_window(self):
        """Minimize/hide window to system tray."""
        if self.window:
            try:
                self.window.hide()
                system_tray.notify(
                    "Productify Node",
                    "Application minimized to system tray. Workloads and thermal guard remain active."
                )
            except Exception as e:
                logger.debug(f"Error hiding window: {e}")

    def on_closing(self):
        """Intercept close button to minimize to tray instead of abruptly terminating compute."""
        if self._is_closing:
            return True
        logger.info("Window close intercepted -> minimizing to system tray.")
        self.hide_window()
        return False  # Prevent window destruction

    def force_exit(self):
        """Clean shutdown invoked from Tray or system signal."""
        self._is_closing = True
        thermal_guard.stop()
        tunnel_daemon.stop()
        local_bridge.stop()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass

    def run(self):
        """Launch webview window and initialize services."""
        # Ensure daemons are running
        local_bridge.port = self.port
        local_bridge.start()
        tunnel_daemon.start()
        thermal_guard.start()

        # Start system tray
        system_tray.start(
            show_window_cb=self.show_window,
            exit_cb=self.force_exit
        )
        local_bridge.wait_until_ready(1.5)

        url = f"http://127.0.0.1:{self.port}/ui"
        self.window = webview.create_window(
            title="Productify Node — Provider Hypervisor",
            url=url,
            width=1060,
            height=740,
            min_size=(820, 600),
            background_color="#07090d",
            confirm_close=False,
        )

        self.window.events.closing += self.on_closing

        logger.info("Starting WebView2 engine...")
        webview.start(debug=False)


def start_webview(port=48123):
    app = ProductifyWebViewApp(port=port)
    app.run()


if __name__ == "__main__":
    start_webview()
