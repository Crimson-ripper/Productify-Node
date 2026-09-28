"""Active workloads and live audit log stream tab."""

import tkinter as tk
from tkinter import ttk
from productify_node.gui.theme import (
    BG_CARD, BG_CARD_LIGHT, BORDER_COLOR, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT_LIME, ACCENT_GREEN, ACCENT_CYAN, ACCENT_AMBER, ACCENT_RED,
    FONT_TITLE, FONT_BODY, FONT_BODY_BOLD, FONT_MONO_SMALL
)
from productify_node.state import node_state
from productify_node.container import container_mgr


class LogsTab(tk.Frame):
    """Displays active pod workloads and live audit log stream."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG_CARD)
        self.pack(fill="both", expand=True, padx=12, pady=12)
        self._build_ui()
        node_state.add_log_listener(self._on_new_log)
        node_state.add_listener(self._on_state_change)

    def _build_ui(self):
        # 1. Active Pods Section
        pod_header = tk.Frame(self, bg=BG_CARD)
        pod_header.pack(fill="x", pady=(0, 4))

        tk.Label(pod_header, text="ACTIVE RUNNING PODS & WORKLOADS", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")
        self.pod_count_lbl = tk.Label(pod_header, text="0 Active", font=FONT_BODY_BOLD, fg=ACCENT_LIME, bg=BG_CARD)
        self.pod_count_lbl.pack(side="right")

        self.pods_box = tk.Text(self, height=4, bg=BG_CARD_LIGHT, fg=TEXT_PRIMARY, font=FONT_MONO_SMALL, highlightbackground=BORDER_COLOR, highlightthickness=1, relief="flat", padx=8, pady=6)
        self.pods_box.insert("end", "No active container workloads currently running on node.\n")
        self.pods_box.config(state="disabled")
        self.pods_box.pack(fill="x", pady=(0, 10))

        # 2. Live Audit Logs Header & Action buttons
        log_header = tk.Frame(self, bg=BG_CARD)
        log_header.pack(fill="x", pady=(4, 4))

        tk.Label(log_header, text="LIVE HYPERVISOR AUDIT LOG", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")

        clear_btn = tk.Button(
            log_header,
            text="Clear",
            font=FONT_BODY,
            fg=TEXT_MUTED,
            bg=BG_CARD_LIGHT,
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._clear_logs,
        )
        clear_btn.pack(side="right", padx=(6, 0))

        emergency_btn = tk.Button(
            log_header,
            text="🚨 Emergency Stop & Wipe",
            font=FONT_BODY_BOLD,
            fg="#ffffff",
            bg=ACCENT_RED,
            activebackground="#dc2626",
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
            command=self._emergency_stop,
        )
        emergency_btn.pack(side="right")

        # 3. Terminal Log Box
        self.log_text = tk.Text(
            self,
            bg="#080a0d",
            fg="#e2e8f0",
            font=FONT_MONO_SMALL,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
            relief="flat",
            padx=10,
            pady=8,
        )
        self.log_text.tag_config("INFO", foreground="#38bdf8")
        self.log_text.tag_config("WARNING", foreground="#f59e0b")
        self.log_text.tag_config("ERROR", foreground="#ef4444")
        self.log_text.tag_config("TIME", foreground="#64748b")
        self.log_text.pack(fill="both", expand=True)

        # Populate existing logs
        for entry in node_state.get_logs(50):
            self._render_log_entry(entry)

    def _render_log_entry(self, entry):
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{entry['time']}] ", "TIME")
        self.log_text.insert("end", f"{entry['text']}\n", entry.get("level", "INFO"))
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _on_new_log(self, entry):
        self._render_log_entry(entry)

    def _on_state_change(self, state):
        pods = state.get_active_pods()
        count = len(pods)
        self.pod_count_lbl.config(text=f"{count} Active" if count else "0 Active")

        self.pods_box.config(state="normal")
        self.pods_box.delete("1.0", "end")
        if not pods:
            self.pods_box.insert("end", "No active container workloads currently running on node.\n")
        else:
            for pid, info in pods.items():
                self.pods_box.insert("end", f"• Pod {pid} | Container: {info.get('container_id')} | Image: {info.get('image')}\n")
        self.pods_box.config(state="disabled")

    def _clear_logs(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _emergency_stop(self):
        count = container_mgr.destroy_all_pods()
        node_state.log(f"Manual Emergency Stop triggered: {count} pod(s) terminated and scratch disks purged.", "WARNING")
