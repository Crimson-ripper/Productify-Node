"""Ultra-comfortable Modern Desktop GUI for Productify Node using CustomTkinter."""

import os
import webbrowser
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from productify_node.config import config
from productify_node.state import node_state
from productify_node.boundary import enforcer
from productify_node.telemetry import get_full_telemetry
from productify_node.auth import auth_client
from productify_node.container import container_mgr
from productify_node.tunnel import tunnel_daemon
from productify_node.bridge.local_server import local_bridge
from productify_node.thermal_guard import thermal_guard
from productify_node.tray import system_tray

# Visual theme constants
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

BG_DARK = "#090b0e"
BG_CARD = "#13171f"
BG_CARD_LIGHT = "#1a202c"
BORDER_COLOR = "#2d3748"
ACCENT_LIME = "#c8f04c"
ACCENT_GREEN = "#10b981"
ACCENT_AMBER = "#f59e0b"
ACCENT_RED = "#ef4444"
ACCENT_CYAN = "#38bdf8"
TEXT_MUTED = "#94a3b8"


class ProductifyModernApp(ctk.CTk):
    """Modern, high-comfort desktop GUI for Productify Node."""

    def __init__(self):
        super().__init__()
        self.title("Productify Node — Physical Compute & GPU Provider")
        self.geometry("900x680")
        self.minsize(820, 600)
        self.configure(fg_color=BG_DARK)

        enforcer.refresh_hardware_limits()
        self.max_ram = enforcer.max_allowable_ram_gb
        self.max_disk = enforcer.max_allowable_disk_gb
        self.max_cpus = enforcer.max_allowable_cpus

        # Start background daemons
        local_bridge.start()
        tunnel_daemon.start()
        thermal_guard.start()
        system_tray.start(show_window_cb=self._show_window, exit_cb=self._force_exit)

        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._build_header()
        self._build_navigation()
        self._build_tabs()
        self._build_footer()

        # Listen for state changes
        node_state.add_listener(self._on_state_change)
        node_state.add_log_listener(self._on_new_log)
        self._update_live_ui()

        # Periodic telemetry tick
        self.after(5000, self._periodic_tick)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
        header.pack(fill="x", padx=16, pady=(16, 10))

        # Brand / Left
        left_box = ctk.CTkFrame(header, fg_color="transparent")
        left_box.pack(side="left", padx=18, pady=14)

        title_lbl = ctk.CTkLabel(
            left_box,
            text="⚡ PRODUCTIFY NODE",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=ACCENT_LIME
        )
        title_lbl.pack(anchor="w")

        id_box = ctk.CTkFrame(left_box, fg_color="transparent")
        id_box.pack(anchor="w", pady=(2, 0))

        sub_lbl = ctk.CTkLabel(
            id_box,
            text=f"Node: {config.node_id} ",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=TEXT_MUTED
        )
        sub_lbl.pack(side="left")

        copy_btn = ctk.CTkButton(
            id_box,
            text="Copy",
            width=46,
            height=20,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=BG_CARD_LIGHT,
            hover_color="#2b3545",
            command=self._copy_node_id
        )
        copy_btn.pack(side="left", padx=4)

        # LIVE / PAUSE Switch / Right
        right_box = ctk.CTkFrame(header, fg_color="transparent")
        right_box.pack(side="right", padx=18, pady=14)

        self.live_btn = ctk.CTkButton(
            right_box,
            text="🟢 LIVE (Accepting Workloads)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=42,
            corner_radius=10,
            command=self._toggle_live_pause
        )
        self.live_btn.pack()

    def _build_navigation(self):
        nav_box = ctk.CTkFrame(self, fg_color="transparent")
        nav_box.pack(fill="x", padx=16, pady=(0, 10))

        self.seg_btn = ctk.CTkSegmentedButton(
            nav_box,
            values=[
                "📊 Hardware Dashboard",
                "🛡️ Memory & Space Allocation",
                "🔑 Authentication",
                "📋 Pods & Live Logs"
            ],
            command=self._on_tab_select,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=36,
            selected_color=BG_CARD_LIGHT,
            selected_hover_color="#283243",
            unselected_color=BG_CARD,
            unselected_hover_color="#1c232f",
            corner_radius=10
        )
        self.seg_btn.set("📊 Hardware Dashboard")
        self.seg_btn.pack(fill="x")

    def _build_tabs(self):
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # 1. Dashboard Tab Frame
        self.frame_dash = ctk.CTkFrame(self.content_container, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
        self._init_dashboard_tab()

        # 2. Allocation Tab Frame
        self.frame_alloc = ctk.CTkFrame(self.content_container, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
        self._init_allocation_tab()

        # 3. Authentication Tab Frame
        self.frame_auth = ctk.CTkFrame(self.content_container, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
        self._init_auth_tab()

        # 4. Logs Tab Frame
        self.frame_logs = ctk.CTkFrame(self.content_container, fg_color=BG_CARD, corner_radius=14, border_width=1, border_color=BORDER_COLOR)
        self._init_logs_tab()

        # Show initial tab
        self.frame_dash.pack(fill="both", expand=True)

    def _init_dashboard_tab(self):
        f = self.frame_dash

        # Grid of 4 rounded cards
        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=16, pady=16)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_rowconfigure(1, weight=1)

        # Card 1: GPU
        c1 = ctk.CTkFrame(grid, fg_color=BG_CARD_LIGHT, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        c1.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(c1, text="■ GPU ACCELERATION", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_LIME).pack(anchor="w", padx=16, pady=(14, 4))
        self.dash_gpu_name = ctk.CTkLabel(c1, text="Detecting...", font=ctk.CTkFont(size=16, weight="bold"))
        self.dash_gpu_name.pack(anchor="w", padx=16)
        self.dash_gpu_sub = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self.dash_gpu_sub.pack(anchor="w", padx=16, pady=(2, 10))

        # Card 2: CPU
        c2 = ctk.CTkFrame(grid, fg_color=BG_CARD_LIGHT, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        c2.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(c2, text="■ CPU PROCESSOR", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_CYAN).pack(anchor="w", padx=16, pady=(14, 4))
        self.dash_cpu_name = ctk.CTkLabel(c2, text="Detecting...", font=ctk.CTkFont(size=15, weight="bold"), wraplength=340)
        self.dash_cpu_name.pack(anchor="w", padx=16)
        self.dash_cpu_sub = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self.dash_cpu_sub.pack(anchor="w", padx=16, pady=(2, 10))

        # Card 3: RAM
        c3 = ctk.CTkFrame(grid, fg_color=BG_CARD_LIGHT, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        c3.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(c3, text="■ SYSTEM RAM ALLOCATION", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_GREEN).pack(anchor="w", padx=16, pady=(14, 4))
        self.dash_ram_val = ctk.CTkLabel(c3, text="Detecting...", font=ctk.CTkFont(size=16, weight="bold"))
        self.dash_ram_val.pack(anchor="w", padx=16)
        self.dash_ram_sub = ctk.CTkLabel(c3, text="", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self.dash_ram_sub.pack(anchor="w", padx=16, pady=(2, 10))

        # Card 4: Disk
        c4 = ctk.CTkFrame(grid, fg_color=BG_CARD_LIGHT, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        c4.grid(row=1, column=1, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(c4, text="■ STORAGE & SCRATCH ALLOCATION", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_AMBER).pack(anchor="w", padx=16, pady=(14, 4))
        self.dash_disk_val = ctk.CTkLabel(c4, text="Detecting...", font=ctk.CTkFont(size=16, weight="bold"))
        self.dash_disk_val.pack(anchor="w", padx=16)
        self.dash_disk_sub = ctk.CTkLabel(c4, text="", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self.dash_disk_sub.pack(anchor="w", padx=16, pady=(2, 10))

        self._refresh_dashboard_telemetry()

    def _init_allocation_tab(self):
        f = self.frame_alloc

        scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=16)

        # Description
        desc_box = ctk.CTkFrame(scroll, fg_color=BG_CARD_LIGHT, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        desc_box.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            desc_box,
            text="🛡️ RESOURCE BOUNDARY SPECIFICATION\n"
                 "Predetermine the exact RAM and disk space you are willing to give. "
                 "Productify workloads are strictly restricted to perform within your set boundaries.",
            font=ctk.CTkFont(size=12),
            text_color="#e2e8f0",
            justify="left"
        ).pack(anchor="w", padx=16, pady=12)

        # 1. RAM Allocation Section
        ram_card = ctk.CTkFrame(scroll, fg_color=BG_CARD_LIGHT, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        ram_card.pack(fill="x", pady=8)

        ram_top = ctk.CTkFrame(ram_card, fg_color="transparent")
        ram_top.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkLabel(ram_top, text="Dedicated RAM Memory Limit", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self.alloc_ram_badge = ctk.CTkLabel(ram_top, text=f"{config.ram_limit_gb:.1f} GB", font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT_LIME)
        self.alloc_ram_badge.pack(side="right")

        self.slider_ram = ctk.CTkSlider(
            ram_card,
            from_=0.5,
            to=self.max_ram,
            number_of_steps=int(max(1, (self.max_ram - 0.5) * 2)),
            command=self._on_ram_slider_change
        )
        self.slider_ram.set(min(config.ram_limit_gb, self.max_ram))
        self.slider_ram.pack(fill="x", padx=18, pady=8)

        # Quick preset buttons for RAM
        preset_box = ctk.CTkFrame(ram_card, fg_color="transparent")
        preset_box.pack(anchor="w", padx=18, pady=(0, 12))
        ctk.CTkLabel(preset_box, text="Quick Presets: ", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="left")

        ctk.CTkButton(preset_box, text="🌱 Eco (1.0 GB)", width=90, height=24, font=ctk.CTkFont(size=11), fg_color="#232a36", command=lambda: self._set_ram_preset(1.0)).pack(side="left", padx=4)
        ctk.CTkButton(preset_box, text="⚖️ Balanced (2.0 GB)", width=110, height=24, font=ctk.CTkFont(size=11), fg_color="#232a36", command=lambda: self._set_ram_preset(2.0)).pack(side="left", padx=4)
        ctk.CTkButton(preset_box, text=f"🚀 High ({self.max_ram:.1f} GB)", width=100, height=24, font=ctk.CTkFont(size=11), fg_color="#232a36", command=lambda: self._set_ram_preset(self.max_ram)).pack(side="left", padx=4)

        # 2. Disk Allocation Section
        disk_card = ctk.CTkFrame(scroll, fg_color=BG_CARD_LIGHT, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        disk_card.pack(fill="x", pady=8)

        disk_top = ctk.CTkFrame(disk_card, fg_color="transparent")
        disk_top.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkLabel(disk_top, text="Scratch Disk Storage Limit", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self.alloc_disk_badge = ctk.CTkLabel(disk_top, text=f"{config.disk_limit_gb:.1f} GB", font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT_AMBER)
        self.alloc_disk_badge.pack(side="right")

        self.slider_disk = ctk.CTkSlider(
            disk_card,
            from_=2.0,
            to=max(10.0, self.max_disk),
            number_of_steps=20,
            command=self._on_disk_slider_change
        )
        self.slider_disk.set(min(config.disk_limit_gb, self.max_disk))
        self.slider_disk.pack(fill="x", padx=18, pady=8)

        disk_presets = ctk.CTkFrame(disk_card, fg_color="transparent")
        disk_presets.pack(anchor="w", padx=18, pady=(0, 12))
        ctk.CTkLabel(disk_presets, text="Quick Presets: ", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="left")
        ctk.CTkButton(disk_presets, text="10 GB", width=60, height=24, font=ctk.CTkFont(size=11), fg_color="#232a36", command=lambda: self._set_disk_preset(10.0)).pack(side="left", padx=4)
        ctk.CTkButton(disk_presets, text="25 GB", width=60, height=24, font=ctk.CTkFont(size=11), fg_color="#232a36", command=lambda: self._set_disk_preset(25.0)).pack(side="left", padx=4)
        ctk.CTkButton(disk_presets, text="50 GB", width=60, height=24, font=ctk.CTkFont(size=11), fg_color="#232a36", command=lambda: self._set_disk_preset(50.0)).pack(side="left", padx=4)

        # 3. Containment Switches
        sw_card = ctk.CTkFrame(scroll, fg_color=BG_CARD_LIGHT, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        sw_card.pack(fill="x", pady=8)

        self.sw_cgroups = ctk.CTkSwitch(sw_card, text="Strict Docker Cgroups (--memory, --memory-swap, --cpus)", font=ctk.CTkFont(size=12))
        self.sw_cgroups.select()
        self.sw_cgroups.pack(anchor="w", padx=18, pady=(14, 8))

        self.sw_quota = ctk.CTkSwitch(sw_card, text="Active Disk Quota Watcher (Auto-abort workloads that exceed scratch limit)", font=ctk.CTkFont(size=12))
        self.sw_quota.select()
        self.sw_quota.pack(anchor="w", padx=18, pady=(0, 14))

        # Save Button
        save_box = ctk.CTkFrame(scroll, fg_color="transparent")
        save_box.pack(fill="x", pady=12)

        save_btn = ctk.CTkButton(
            save_box,
            text="💾 Save & Lock Resource Boundaries",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT_LIME,
            text_color="#101112",
            hover_color="#b6dc3e",
            height=40,
            corner_radius=10,
            command=self._save_boundaries
        )
        save_btn.pack(side="left")

        self.save_feedback = ctk.CTkLabel(save_box, text="", font=ctk.CTkFont(size=12), text_color=ACCENT_GREEN)
        self.save_feedback.pack(side="left", padx=14)

    def _init_auth_tab(self):
        f = self.frame_auth
        scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(scroll, text="Platform Configuration", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.entry_url = ctk.CTkEntry(scroll, height=36, corner_radius=8)
        self.entry_url.insert(0, config.get("platform_url", "https://productifynow.com"))
        self.entry_url.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(scroll, text="Host Pairing Token (from Seller Dashboard)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.entry_token = ctk.CTkEntry(scroll, height=36, corner_radius=8, show="*")
        self.entry_token.insert(0, config.get("pairing_token", ""))
        self.entry_token.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(scroll, text="Assigned Rental ID (optional)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.entry_rental = ctk.CTkEntry(scroll, height=36, corner_radius=8)
        self.entry_rental.insert(0, config.get("rental_id", ""))
        self.entry_rental.pack(fill="x", pady=(0, 16))

        # Action Buttons
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", pady=6)

        pair_btn = ctk.CTkButton(
            btn_row,
            text="⚡ Authenticate & Pair Node",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT_LIME,
            text_color="#101112",
            hover_color="#b6dc3e",
            height=38,
            corner_radius=8,
            command=self._pair_system
        )
        pair_btn.pack(side="left", padx=(0, 10))

        test_btn = ctk.CTkButton(
            btn_row,
            text="📡 Test Reachability",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BG_CARD_LIGHT,
            hover_color="#2b3545",
            height=38,
            corner_radius=8,
            command=self._test_platform
        )
        test_btn.pack(side="left", padx=(0, 10))

        web_btn = ctk.CTkButton(
            btn_row,
            text="🌐 Open In-Browser Dashboard",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BG_CARD_LIGHT,
            hover_color="#2b3545",
            height=38,
            corner_radius=8,
            command=lambda: webbrowser.open("http://127.0.0.1:48123/ui")
        )
        web_btn.pack(side="left")

        self.auth_feedback = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=12), wraplength=550)
        self.auth_feedback.pack(anchor="w", pady=12)

    def _init_logs_tab(self):
        f = self.frame_logs
        box = ctk.CTkFrame(f, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=16, pady=16)

        # Header with Emergency Stop
        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(top, text="LIVE HYPERVISOR AUDIT LOG", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")

        clear_btn = ctk.CTkButton(
            top,
            text="Clear",
            width=60,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=BG_CARD_LIGHT,
            hover_color="#2b3545",
            command=self._clear_logs
        )
        clear_btn.pack(side="right", padx=(8, 0))

        emer_btn = ctk.CTkButton(
            top,
            text="🚨 Emergency Stop & Wipe",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT_RED,
            hover_color="#dc2626",
            height=28,
            command=self._emergency_stop
        )
        emer_btn.pack(side="right")

        # Terminal text area
        self.txt_logs = ctk.CTkTextbox(
            box,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#06080b",
            text_color="#cbd5e1",
            corner_radius=10,
            border_width=1,
            border_color=BORDER_COLOR
        )
        self.txt_logs.pack(fill="both", expand=True)

        for e in node_state.get_logs(50):
            self.txt_logs.insert("end", f"[{e['time']}] {e['text']}\n")
        self.txt_logs.see("end")

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=BG_CARD, height=32, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        footer.pack(fill="x", padx=16, pady=(0, 12))

        self.foot_status = ctk.CTkLabel(
            footer,
            text="Local Bridge: http://127.0.0.1:48123/ui · Tunnel: Active",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED
        )
        self.foot_status.pack(side="left", padx=16, pady=4)

        self.foot_limits = ctk.CTkLabel(
            footer,
            text=f"Locked Boundaries: {config.ram_limit_gb:.1f}GB RAM · {config.disk_limit_gb:.1f}GB Disk",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT_LIME
        )
        self.foot_limits.pack(side="right", padx=16, pady=4)

    # ---------------- Interactions & Callbacks ----------------
    def _on_tab_select(self, val):
        self.frame_dash.pack_forget()
        self.frame_alloc.pack_forget()
        self.frame_auth.pack_forget()
        self.frame_logs.pack_forget()

        if "Dashboard" in val:
            self.frame_dash.pack(fill="both", expand=True)
            self._refresh_dashboard_telemetry()
        elif "Allocation" in val:
            self.frame_alloc.pack(fill="both", expand=True)
        elif "Authentication" in val:
            self.frame_auth.pack(fill="both", expand=True)
        elif "Logs" in val:
            self.frame_logs.pack(fill="both", expand=True)

    def _toggle_live_pause(self):
        node_state.toggle_live_pause()
        self._update_live_ui()

    def _update_live_ui(self):
        if node_state.is_live:
            self.live_btn.configure(
                text="🟢 LIVE (Accepting Workloads)",
                fg_color=ACCENT_GREEN,
                hover_color="#059669",
                text_color="#ffffff"
            )
            self.foot_status.configure(text=f"Bridge: http://127.0.0.1:48123/ui · Tunnel: {'CONNECTED' if node_state.tunnel_connected else 'ONLINE (Advertising)'}")
        else:
            self.live_btn.configure(
                text="⏸️ PAUSED (Machine Safe / Offline)",
                fg_color="#334155",
                hover_color="#475569",
                text_color="#cbd5e1"
            )
            self.foot_status.configure(text="Bridge: http://127.0.0.1:48123/ui · Tunnel: SUSPENDED (Paused)")

    def _on_ram_slider_change(self, val):
        self.alloc_ram_badge.configure(text=f"{val:.1f} GB")

    def _on_disk_slider_change(self, val):
        self.alloc_disk_badge.configure(text=f"{val:.1f} GB")

    def _set_ram_preset(self, gb):
        val = min(gb, self.max_ram)
        self.slider_ram.set(val)
        self.alloc_ram_badge.configure(text=f"{val:.1f} GB")

    def _set_disk_preset(self, gb):
        val = min(gb, self.max_disk)
        self.slider_disk.set(val)
        self.alloc_disk_badge.configure(text=f"{val:.1f} GB")

    def _save_boundaries(self):
        ram = round(float(self.slider_ram.get()), 1)
        disk = round(float(self.slider_disk.get()), 1)
        res = enforcer.set_allocations(ram, disk)
        self.save_feedback.configure(text="✓ Boundaries saved and locked to container engine!")
        self.foot_limits.configure(text=f"Locked Boundaries: {res['ram_limit_gb']:.1f}GB RAM · {res['disk_limit_gb']:.1f}GB Disk")
        self.after(3500, lambda: self.save_feedback.configure(text=""))

    def _pair_system(self):
        url = self.entry_url.get().strip()
        tok = self.entry_token.get().strip()
        rent = self.entry_rental.get().strip()
        if not tok:
            self.auth_feedback.configure(text="⚠️ Please enter a Pairing Token from your Productify account.", text_color=ACCENT_AMBER)
            return

        self.auth_feedback.configure(text="Authenticating with Productify Cloud...", text_color=TEXT_MUTED)
        self.update()
        res = auth_client.pair_with_token(tok, rental_id=rent, platform_url=url)
        if res.get("ok"):
            self.auth_feedback.configure(text="✓ Node successfully paired with Productify platform!", text_color=ACCENT_GREEN)
        else:
            self.auth_feedback.configure(text=f"Authentication error: {res.get('error')}", text_color=ACCENT_RED)

    def _test_platform(self):
        url = self.entry_url.get().strip()
        res = auth_client.test_platform_connection(url)
        if res.get("reachable"):
            self.auth_feedback.configure(text=f"✓ Platform is reachable! (HTTP status: {res.get('status_code')})", text_color=ACCENT_GREEN)
        else:
            self.auth_feedback.configure(text=f"❌ Unable to reach platform: {res.get('error')}", text_color=ACCENT_RED)

    def _refresh_dashboard_telemetry(self):
        t = get_full_telemetry()
        gpu = t["gpu"]
        if gpu["available"]:
            self.dash_gpu_name.configure(text=gpu["name"])
            self.dash_gpu_sub.configure(text=f"VRAM: {gpu['vram_used_mb']:.0f} MB / {gpu['vram_total_mb']:.0f} MB · Core Temp: {gpu['temperature_c']}°C · Driver: {gpu['driver_version']}")
        else:
            self.dash_gpu_name.configure(text="CPU Mode (No NVIDIA GPU)")
            self.dash_gpu_sub.configure(text="Workloads will execute on high-speed CPU threads")

        cpu = t["cpu"]
        self.dash_cpu_name.configure(text=cpu["name"])
        self.dash_cpu_sub.configure(text=f"{cpu['cores']} Logical Cores · Allocated: {config.cpu_limit_cores} Core(s)")

        ram = t["ram"]
        self.dash_ram_val.configure(text=f"{ram['total_gb']} GB Physical RAM")
        self.dash_ram_sub.configure(text=f"Allocated: {config.ram_limit_gb:.1f} GB Max · Free: {ram['free_gb']} GB")

        disk = t["disk"]
        self.dash_disk_val.configure(text=f"{disk['free_gb']} GB Free Storage")
        self.dash_disk_sub.configure(text=f"Scratch Quota: {config.disk_limit_gb:.1f} GB Max · Mount: ~/.productify/pods")

    def _on_state_change(self, state):
        self._update_live_ui()
        self.foot_limits.configure(text=f"Locked Boundaries: {config.ram_limit_gb:.1f}GB RAM · {config.disk_limit_gb:.1f}GB Disk")

    def _on_new_log(self, entry):
        try:
            self.txt_logs.insert("end", f"[{entry['time']}] {entry['text']}\n")
            self.txt_logs.see("end")
        except Exception:
            pass

    def _clear_logs(self):
        self.txt_logs.delete("1.0", "end")

    def _emergency_stop(self):
        count = container_mgr.destroy_all_pods()
        messagebox.showwarning("Emergency Stop", f"All active workloads ({count}) terminated and scratch disks purged clean.")

    def _copy_node_id(self):
        self.clipboard_clear()
        self.clipboard_append(config.node_id)
        messagebox.showinfo("Copied", f"Node ID '{config.node_id}' copied to clipboard.")

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

    def _periodic_tick(self):
        try:
            self._refresh_dashboard_telemetry()
        except Exception:
            pass
        self._update_live_ui()
        self.after(6000, self._periodic_tick)


def start_app():
    app = ProductifyModernApp()
    app.mainloop()


if __name__ == "__main__":
    start_app()
