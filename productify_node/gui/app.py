"""Main Desktop GUI application window for Productify Node."""

import tkinter as tk
from tkinter import ttk
import logging
from productify_node.gui.theme import (
    BG_DARK, BG_CARD, BG_CARD_LIGHT, BORDER_COLOR, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT_LIME, ACCENT_GREEN, ACCENT_AMBER, ACCENT_RED, ACCENT_CYAN,
    FONT_HEADING, FONT_TITLE, FONT_BODY, FONT_BODY_BOLD, FONT_MONO
)
from productify_node.gui.tabs_dashboard import DashboardTab
from productify_node.gui.tabs_allocation import AllocationTab
from productify_node.gui.tabs_auth import AuthTab
from productify_node.gui.tabs_logs import LogsTab
from productify_node.state import node_state
from productify_node.config import config
from productify_node.tunnel import tunnel_daemon
from productify_node.bridge.local_server import local_bridge
from productify_node.thermal_guard import thermal_guard
from productify_node.tray import system_tray

logger = logging.getLogger("productify_node.gui")


class ProductifyNodeApp(tk.Tk):
    """Productify Node Desktop Application."""

    def __init__(self):
        super().__init__()
        self.title("Productify Node — Physical GPU & Compute Provider")
        self.geometry("860x640")
        self.minsize(780, 560)
        self.configure(bg=BG_DARK)

        # Start background daemons
        local_bridge.start()
        tunnel_daemon.start()
        thermal_guard.start()
        system_tray.start(show_window_cb=self._show_window, exit_cb=self._force_exit)
        try:
            from productify_node.streaming.sunshine_mgr import sunshine_mgr
            sunshine_mgr.ensure_web_server_running(48080)
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._build_header()
        self._build_tabs()
        self._build_footer()

        # Listen to state changes
        node_state.add_listener(self._on_state_change)
        self._update_live_button_state()

        # Periodic refresh
        self.after(5000, self._periodic_tick)

    def _build_header(self):
        header = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        header.pack(fill="x", padx=12, pady=(12, 6))

        # Brand & Node details (Left)
        brand_frame = tk.Frame(header, bg=BG_CARD)
        brand_frame.pack(side="left", padx=16, pady=12)

        title_frame = tk.Frame(brand_frame, bg=BG_CARD)
        title_frame.pack(anchor="w")

        tk.Label(title_frame, text="⚡ PRODUCTIFY", font=FONT_HEADING, fg=ACCENT_LIME, bg=BG_CARD).pack(side="left")
        tk.Label(title_frame, text=" NODE", font=FONT_HEADING, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")

        sub_frame = tk.Frame(brand_frame, bg=BG_CARD)
        sub_frame.pack(anchor="w", pady=(2, 0))
        tk.Label(sub_frame, text="Host Hypervisor · ID: ", font=FONT_BODY, fg=TEXT_MUTED, bg=BG_CARD).pack(side="left")
        tk.Label(sub_frame, text=config.node_id, font=FONT_MONO, fg=ACCENT_CYAN, bg=BG_CARD).pack(side="left")

        # LIVE / PAUSE Switch (Right)
        right_frame = tk.Frame(header, bg=BG_CARD)
        right_frame.pack(side="right", padx=16, pady=12)

        self.live_btn = tk.Button(
            right_frame,
            text="● LIVE (Earning)",
            font=FONT_HEADING,
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._toggle_live_pause
        )
        self.live_btn.pack()

    def _build_tabs(self):
        # Configure Notebook / Tab Styling
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG_CARD,
            foreground=TEXT_MUTED,
            padding=[16, 8],
            font=FONT_TITLE,
            borderwidth=0
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_CARD_LIGHT)],
            foreground=[("selected", TEXT_PRIMARY)],
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=6)

        # Tab 1: Dashboard
        self.tab_dash = DashboardTab(self.notebook)
        self.notebook.add(self.tab_dash, text="  📊 Hardware Dashboard  ")

        # Tab 2: Memory & Space Allocation (User's primary request)
        self.tab_alloc = AllocationTab(self.notebook)
        self.notebook.add(self.tab_alloc, text="  🛡️ Memory & Space Allocation  ")

        # Tab 3: System Authentication
        self.tab_auth = AuthTab(self.notebook)
        self.notebook.add(self.tab_auth, text="  🔑 System Authentication  ")

        # Tab 4: Active Pods & Logs
        self.tab_logs = LogsTab(self.notebook)
        self.notebook.add(self.tab_logs, text="  📋 Active Pods & Logs  ")

    def _build_footer(self):
        footer = tk.Frame(self, bg=BG_CARD, height=28, highlightbackground=BORDER_COLOR, highlightthickness=1)
        footer.pack(fill="x", padx=12, pady=(0, 10))

        # Left status
        self.footer_status = tk.Label(footer, text="Bridge active: http://127.0.0.1:48123 · Tunnel: Idle", font=FONT_BODY, fg=TEXT_MUTED, bg=BG_CARD)
        self.footer_status.pack(side="left", padx=12, pady=4)

        # Right limits summary
        self.footer_limits = tk.Label(footer, text=f"Boundaries: {config.ram_limit_gb}GB RAM · {config.disk_limit_gb}GB Disk", font=FONT_BODY_BOLD, fg=ACCENT_LIME, bg=BG_CARD)
        self.footer_limits.pack(side="right", padx=12, pady=4)

    def _toggle_live_pause(self):
        node_state.toggle_live_pause()
        self._update_live_button_state()

    def _update_live_button_state(self):
        if node_state.is_live:
            self.live_btn.config(
                text="🟢 LIVE (Available on Marketplace)",
                bg=ACCENT_GREEN,
                fg="#ffffff",
                activebackground="#059669",
                activeforeground="#ffffff"
            )
            self.footer_status.config(text=f"Bridge: http://127.0.0.1:48123 · Tunnel: {'CONNECTED' if node_state.tunnel_connected else 'ONLINE (Advertising)'}")
        else:
            self.live_btn.config(
                text="⏸️ PAUSED (Machine Offline / Safe)",
                bg="#374151",
                fg="#d1d5db",
                activebackground="#4b5563",
                activeforeground="#ffffff"
            )
            self.footer_status.config(text="Bridge: http://127.0.0.1:48123 · Tunnel: SUSPENDED (Paused)")

    def _on_state_change(self, state):
        self._update_live_button_state()
        self.footer_limits.config(text=f"Boundaries: {config.ram_limit_gb}GB RAM · {config.disk_limit_gb}GB Disk")

    def _periodic_tick(self):
        # Refresh dashboard telemetry
        try:
            self.tab_dash.refresh()
        except Exception:
            pass
        self._update_live_button_state()
    def _show_window(self):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _on_close_window(self):
        self.withdraw()
        system_tray.notify(
            "Productify Node",
            "Application minimized to system tray. Workloads and thermal guard remain active."
        )

    def _force_exit(self):
        thermal_guard.stop()
        tunnel_daemon.stop()
        local_bridge.stop()
        self.after(0, self.destroy)


def start_gui():
    """Launch modern CustomTkinter hypervisor studio, falling back to Tkinter."""
    try:
        import customtkinter
        from productify_node.gui.ctk_app import start_app as start_modern_app
        logger.info("Initializing CustomTkinter Desktop Hypervisor Studio...")
        start_modern_app()
        return
    except Exception as e:
        logger.warning(f"CustomTkinter launcher skipped ({e}). Falling back to standard Tkinter...")

    try:
        app = ProductifyNodeApp()
        app.mainloop()
    except Exception as e:
        logger.error(f"Fatal error starting GUI: {e}")
        raise


if __name__ == "__main__":
    start_gui()

