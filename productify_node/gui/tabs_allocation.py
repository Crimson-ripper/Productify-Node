"""Memory and Space Allocation tab for setting host resource boundaries."""

import tkinter as tk
from tkinter import ttk
from productify_node.gui.theme import (
    BG_CARD, BG_CARD_LIGHT, BORDER_COLOR, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT_LIME, ACCENT_GREEN, ACCENT_CYAN, ACCENT_AMBER,
    FONT_TITLE, FONT_BODY, FONT_BODY_BOLD, FONT_MONO
)
from productify_node.config import config
from productify_node.boundary import enforcer
from productify_node.state import node_state


class AllocationTab(tk.Frame):
    """Allows host to predetermine RAM, Disk, and CPU boundaries."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG_CARD)
        self.pack(fill="both", expand=True, padx=16, pady=16)

        enforcer.refresh_hardware_limits()
        self.max_ram = enforcer.max_allowable_ram_gb
        self.max_disk = enforcer.max_allowable_disk_gb
        self.max_cpus = enforcer.max_allowable_cpus

        self._build_ui()

    def _build_ui(self):
        # Description banner
        desc_box = tk.Frame(self, bg=BG_CARD_LIGHT, highlightbackground=BORDER_COLOR, highlightthickness=1)
        desc_box.pack(fill="x", pady=(0, 16), padx=4)

        desc_lbl = tk.Label(
            desc_box,
            text="🛡️ RESOURCE BOUNDARY SPECIFICATION\n"
                 "Predetermine the exact RAM and disk space your machine is willing to share. "
                 "Productify will be strictly restricted to perform within your set boundaries.",
            font=FONT_BODY,
            fg=TEXT_PRIMARY,
            bg=BG_CARD_LIGHT,
            justify="left",
            padx=14,
            pady=10,
        )
        desc_lbl.pack(anchor="w")

        # Container for sliders
        form = tk.Frame(self, bg=BG_CARD)
        form.pack(fill="both", expand=True, padx=4)

        # 1. RAM Allocation
        ram_frame = tk.Frame(form, bg=BG_CARD)
        ram_frame.pack(fill="x", pady=8)

        ram_header = tk.Frame(ram_frame, bg=BG_CARD)
        ram_header.pack(fill="x")

        tk.Label(ram_header, text="Dedicated RAM Memory Limit:", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")
        self.ram_val_lbl = tk.Label(ram_header, text=f"{config.ram_limit_gb:.1f} GB", font=FONT_BODY_BOLD, fg=ACCENT_LIME, bg=BG_CARD)
        self.ram_val_lbl.pack(side="right")

        self.ram_slider = ttk.Scale(
            ram_frame,
            from_=0.5,
            to=self.max_ram,
            value=min(config.ram_limit_gb, self.max_ram),
            orient="horizontal",
            command=self._on_ram_slide
        )
        self.ram_slider.pack(fill="x", pady=4)

        tk.Label(
            ram_frame,
            text=f"Physical RAM: {enforcer.physical_ram_total} GB · Safe Upper Bound: {self.max_ram} GB (1.5 GB host safety buffer reserved)",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=BG_CARD,
        ).pack(anchor="w")

        # 2. Disk Allocation
        disk_frame = tk.Frame(form, bg=BG_CARD)
        disk_frame.pack(fill="x", pady=12)

        disk_header = tk.Frame(disk_frame, bg=BG_CARD)
        disk_header.pack(fill="x")

        tk.Label(disk_header, text="Scratch Disk Storage Limit:", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")
        self.disk_val_lbl = tk.Label(disk_header, text=f"{config.disk_limit_gb:.1f} GB", font=FONT_BODY_BOLD, fg=ACCENT_AMBER, bg=BG_CARD)
        self.disk_val_lbl.pack(side="right")

        self.disk_slider = ttk.Scale(
            disk_frame,
            from_=2.0,
            to=max(10.0, self.max_disk),
            value=min(config.disk_limit_gb, self.max_disk),
            orient="horizontal",
            command=self._on_disk_slide
        )
        self.disk_slider.pack(fill="x", pady=4)

        tk.Label(
            disk_frame,
            text=f"Free Disk Space: {enforcer.physical_disk_free} GB · Safe Upper Bound: {self.max_disk} GB (5 GB safety buffer reserved)",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=BG_CARD,
        ).pack(anchor="w")

        # 3. CPU Core Allocation
        cpu_frame = tk.Frame(form, bg=BG_CARD)
        cpu_frame.pack(fill="x", pady=8)

        cpu_header = tk.Frame(cpu_frame, bg=BG_CARD)
        cpu_header.pack(fill="x")

        tk.Label(cpu_header, text="CPU Core Allocation:", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")
        self.cpu_val_lbl = tk.Label(cpu_header, text=f"{config.cpu_limit_cores} Core(s)", font=FONT_BODY_BOLD, fg=ACCENT_CYAN, bg=BG_CARD)
        self.cpu_val_lbl.pack(side="right")

        self.cpu_slider = ttk.Scale(
            cpu_frame,
            from_=1,
            to=self.max_cpus,
            value=min(config.cpu_limit_cores, self.max_cpus),
            orient="horizontal",
            command=self._on_cpu_slide
        )
        self.cpu_slider.pack(fill="x", pady=4)

        tk.Label(
            cpu_frame,
            text=f"Available Logical Threads: {enforcer.physical_cpu_cores} · Max Allocatable: {self.max_cpus} (1 core preserved for OS stability)",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=BG_CARD,
        ).pack(anchor="w")

        # Enforcement options
        enf_frame = tk.Frame(form, bg=BG_CARD_LIGHT, highlightbackground=BORDER_COLOR, highlightthickness=1)
        enf_frame.pack(fill="x", pady=14)

        self.cgroup_var = tk.BooleanVar(value=True)
        cgroup_chk = tk.Checkbutton(
            enf_frame,
            text="Enforce Docker Cgroup containment (--memory, --memory-swap, --cpus)",
            variable=self.cgroup_var,
            font=FONT_BODY,
            fg=TEXT_PRIMARY,
            bg=BG_CARD_LIGHT,
            selectcolor="#0f172a",
            activebackground=BG_CARD_LIGHT,
            activeforeground=TEXT_PRIMARY
        )
        cgroup_chk.pack(anchor="w", padx=12, pady=(10, 4))

        self.quota_var = tk.BooleanVar(value=True)
        quota_chk = tk.Checkbutton(
            enf_frame,
            text="Active Disk Quota Watcher (Immediately abort workloads that violate scratch limits)",
            variable=self.quota_var,
            font=FONT_BODY,
            fg=TEXT_PRIMARY,
            bg=BG_CARD_LIGHT,
            selectcolor="#0f172a",
            activebackground=BG_CARD_LIGHT,
            activeforeground=TEXT_PRIMARY
        )
        quota_chk.pack(anchor="w", padx=12, pady=(0, 10))

        # Save Button
        btn_frame = tk.Frame(form, bg=BG_CARD)
        btn_frame.pack(fill="x", pady=6)

        save_btn = tk.Button(
            btn_frame,
            text="💾 Save & Enforce Resource Boundaries",
            font=FONT_BODY_BOLD,
            fg="#101112",
            bg=ACCENT_LIME,
            activebackground="#b3e038",
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            command=self.save_boundaries,
        )
        save_btn.pack(side="left")

        self.save_status = tk.Label(btn_frame, text="", font=FONT_BODY, fg=ACCENT_GREEN, bg=BG_CARD)
        self.save_status.pack(side="left", padx=12)

    def _on_ram_slide(self, val):
        val_f = round(float(val), 1)
        self.ram_val_lbl.config(text=f"{val_f:.1f} GB")

    def _on_disk_slide(self, val):
        val_f = round(float(val), 1)
        self.disk_val_lbl.config(text=f"{val_f:.1f} GB")

    def _on_cpu_slide(self, val):
        val_i = int(round(float(val)))
        self.cpu_val_lbl.config(text=f"{val_i} Core(s)")

    def save_boundaries(self):
        ram = round(float(self.ram_slider.get()), 1)
        disk = round(float(self.disk_slider.get()), 1)
        cpus = int(round(float(self.cpu_slider.get())))

        res = enforcer.set_allocations(ram, disk, cpus)
        node_state.log(f"Host updated boundaries: RAM={res['ram_limit_gb']}GB, Disk={res['disk_limit_gb']}GB, CPUs={res['cpu_limit_cores']}", "INFO")

        self.save_status.config(text="✓ Boundaries saved and locked to container engine!")
        self.after(3000, lambda: self.save_status.config(text=""))
