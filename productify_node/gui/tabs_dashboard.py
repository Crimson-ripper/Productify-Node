"""Dashboard and real-time hardware telemetry tab for Productify Node."""

import tkinter as tk
from tkinter import ttk
from productify_node.gui.theme import (
    BG_CARD, BG_CARD_LIGHT, BORDER_COLOR, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT_LIME, ACCENT_GREEN, ACCENT_CYAN, ACCENT_AMBER,
    FONT_TITLE, FONT_BODY, FONT_BODY_BOLD, FONT_MONO, FONT_BIG
)
from productify_node.telemetry import get_full_telemetry
from productify_node.config import config


class DashboardTab(tk.Frame):
    """Displays live hardware gauges and node telemetry."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG_CARD)
        self.pack(fill="both", expand=True, padx=12, pady=12)
        self.telemetry = get_full_telemetry()
        self._build_ui()

    def _build_ui(self):
        # 2x2 Grid of Cards
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 1. GPU Card
        self.gpu_card = self._create_card(0, 0, "GPU ACCELERATION & TELEMETRY", ACCENT_LIME)
        self.gpu_name_lbl = tk.Label(self.gpu_card, text="Detecting...", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD_LIGHT)
        self.gpu_name_lbl.pack(anchor="w", padx=12, pady=(0, 4))
        self.gpu_vram_lbl = tk.Label(self.gpu_card, text="", font=FONT_BODY, fg=TEXT_MUTED, bg=BG_CARD_LIGHT)
        self.gpu_vram_lbl.pack(anchor="w", padx=12, pady=2)
        self.gpu_temp_lbl = tk.Label(self.gpu_card, text="", font=FONT_BODY, fg=TEXT_MUTED, bg=BG_CARD_LIGHT)
        self.gpu_temp_lbl.pack(anchor="w", padx=12, pady=2)
        self.gpu_driver_lbl = tk.Label(self.gpu_card, text="", font=FONT_MONO, fg=ACCENT_CYAN, bg=BG_CARD_LIGHT)
        self.gpu_driver_lbl.pack(anchor="w", padx=12, pady=4)

        # 2. CPU Card
        self.cpu_card = self._create_card(0, 1, "CPU PROCESSOR CORES", ACCENT_CYAN)
        self.cpu_name_lbl = tk.Label(self.cpu_card, text="Detecting...", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD_LIGHT, wraplength=280)
        self.cpu_name_lbl.pack(anchor="w", padx=12, pady=(0, 4))
        self.cpu_cores_lbl = tk.Label(self.cpu_card, text="", font=FONT_BODY, fg=TEXT_MUTED, bg=BG_CARD_LIGHT)
        self.cpu_cores_lbl.pack(anchor="w", padx=12, pady=2)
        self.cpu_alloc_lbl = tk.Label(self.cpu_card, text="", font=FONT_BODY, fg=ACCENT_LIME, bg=BG_CARD_LIGHT)
        self.cpu_alloc_lbl.pack(anchor="w", padx=12, pady=2)

        # 3. RAM Memory Card
        self.ram_card = self._create_card(1, 0, "SYSTEM RAM ALLOCATION", ACCENT_GREEN)
        self.ram_total_lbl = tk.Label(self.ram_card, text="Detecting...", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD_LIGHT)
        self.ram_total_lbl.pack(anchor="w", padx=12, pady=(0, 4))
        self.ram_alloc_lbl = tk.Label(self.ram_card, text="", font=FONT_BODY_BOLD, fg=ACCENT_LIME, bg=BG_CARD_LIGHT)
        self.ram_alloc_lbl.pack(anchor="w", padx=12, pady=2)
        self.ram_avail_lbl = tk.Label(self.ram_card, text="", font=FONT_BODY, fg=TEXT_MUTED, bg=BG_CARD_LIGHT)
        self.ram_avail_lbl.pack(anchor="w", padx=12, pady=2)

        # 4. Storage Card
        self.disk_card = self._create_card(1, 1, "DISK & SCRATCH ALLOCATION", ACCENT_AMBER)
        self.disk_free_lbl = tk.Label(self.disk_card, text="Detecting...", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD_LIGHT)
        self.disk_free_lbl.pack(anchor="w", padx=12, pady=(0, 4))
        self.disk_alloc_lbl = tk.Label(self.disk_card, text="", font=FONT_BODY_BOLD, fg=ACCENT_AMBER, bg=BG_CARD_LIGHT)
        self.disk_alloc_lbl.pack(anchor="w", padx=12, pady=2)
        self.disk_path_lbl = tk.Label(self.disk_card, text="", font=FONT_MONO, fg=TEXT_MUTED, bg=BG_CARD_LIGHT)
        self.disk_path_lbl.pack(anchor="w", padx=12, pady=2)

        # Refresh with data
        self.refresh()

    def _create_card(self, row, col, title, accent_color):
        card = tk.Frame(self, bg=BG_CARD_LIGHT, highlightbackground=BORDER_COLOR, highlightthickness=1)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

        header = tk.Frame(card, bg=BG_CARD_LIGHT)
        header.pack(fill="x", padx=12, pady=(10, 8))

        indicator = tk.Label(header, text="■", font=("Segoe UI", 8), fg=accent_color, bg=BG_CARD_LIGHT)
        indicator.pack(side="left", padx=(0, 6))

        title_lbl = tk.Label(header, text=title, font=FONT_BODY_BOLD, fg=TEXT_MUTED, bg=BG_CARD_LIGHT)
        title_lbl.pack(side="left")

        return card

    def refresh(self):
        """Update telemetry values on cards."""
        self.telemetry = get_full_telemetry()
        t = self.telemetry

        # GPU
        gpu = t["gpu"]
        if gpu["available"]:
            self.gpu_name_lbl.config(text=gpu["name"])
            self.gpu_vram_lbl.config(text=f"VRAM: {gpu['vram_used_mb']:.0f} MB / {gpu['vram_total_mb']:.0f} MB ({round(gpu['vram_total_mb']/1024, 1)} GB)")
            self.gpu_temp_lbl.config(text=f"Core Temp: {gpu['temperature_c']}°C · Hardware Bridge: Active")
            self.gpu_driver_lbl.config(text=f"Driver: {gpu['driver_version']}")
        else:
            self.gpu_name_lbl.config(text="CPU Mode (No NVIDIA GPU)")
            self.gpu_vram_lbl.config(text="Workloads will execute on high-speed CPU threads")
            self.gpu_temp_lbl.config(text="")
            self.gpu_driver_lbl.config(text="Fallback Sandbox: Ready")

        # CPU
        cpu = t["cpu"]
        self.cpu_name_lbl.config(text=cpu["name"])
        self.cpu_cores_lbl.config(text=f"Hardware Cores: {cpu['cores']} Logical Threads")
        self.cpu_alloc_lbl.config(text=f"Allocated to Node: {config.cpu_limit_cores} Core(s) Bound")

        # RAM
        ram = t["ram"]
        self.ram_total_lbl.config(text=f"{ram['total_gb']} GB Physical RAM")
        self.ram_alloc_lbl.config(text=f"Bounded Allocation: {config.ram_limit_gb} GB Max")
        self.ram_avail_lbl.config(text=f"Free Available: {ram['free_gb']} GB (Host OS reserved)")

        # Disk
        disk = t["disk"]
        self.disk_free_lbl.config(text=f"{disk['free_gb']} GB Free Disk Space")
        self.disk_alloc_lbl.config(text=f"Bounded Scratch: {config.disk_limit_gb} GB Max")
        self.disk_path_lbl.config(text=f"Pod Mount: ~/.productify/pods")
