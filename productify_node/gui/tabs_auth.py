"""System authentication and platform pairing tab."""

import tkinter as tk
from tkinter import ttk
from productify_node.gui.theme import (
    BG_CARD, BG_CARD_LIGHT, BORDER_COLOR, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT_LIME, ACCENT_GREEN, ACCENT_CYAN, ACCENT_AMBER, ACCENT_RED,
    FONT_TITLE, FONT_BODY, FONT_BODY_BOLD, FONT_MONO
)
from productify_node.config import config
from productify_node.auth import auth_client
from productify_node.state import node_state


class AuthTab(tk.Frame):
    """Handles node pairing, tokens, and platform connectivity."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG_CARD)
        self.pack(fill="both", expand=True, padx=16, pady=16)
        self._build_ui()

    def _build_ui(self):
        # Platform Info Box
        info_frame = tk.Frame(self, bg=BG_CARD_LIGHT, highlightbackground=BORDER_COLOR, highlightthickness=1)
        info_frame.pack(fill="x", pady=(0, 16))

        tk.Label(
            info_frame,
            text="🔑 SYSTEM AUTHENTICATION & NODE PAIRING\n"
                 "Link this physical machine to your Productify Seller account. "
                 "Get your Pairing Token from the Seller Dashboard -> 'Deploy / Connect Node'.",
            font=FONT_BODY,
            fg=TEXT_PRIMARY,
            bg=BG_CARD_LIGHT,
            justify="left",
            padx=14,
            pady=10,
        ).pack(anchor="w")

        form = tk.Frame(self, bg=BG_CARD)
        form.pack(fill="both", expand=True)

        # 1. Platform URL
        tk.Label(form, text="Productify Platform URL:", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w", pady=(4, 2))
        self.url_entry = tk.Entry(form, font=FONT_MONO, bg=BG_CARD_LIGHT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.url_entry.insert(0, config.get("platform_url", "https://productifynow.com"))
        self.url_entry.pack(fill="x", pady=(0, 10))

        # 2. Host Pairing Token
        tk.Label(form, text="Host Pairing Token:", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w", pady=(4, 2))
        self.token_entry = tk.Entry(form, font=FONT_MONO, bg=BG_CARD_LIGHT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, highlightthickness=1, highlightbackground=BORDER_COLOR, show="*")
        self.token_entry.insert(0, config.get("pairing_token", ""))
        self.token_entry.pack(fill="x", pady=(0, 10))

        # 3. Rental ID (optional/auto-populated)
        tk.Label(form, text="Assigned Rental Node ID (optional):", font=FONT_TITLE, fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w", pady=(4, 2))
        self.rental_entry = tk.Entry(form, font=FONT_MONO, bg=BG_CARD_LIGHT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.rental_entry.insert(0, config.get("rental_id", ""))
        self.rental_entry.pack(fill="x", pady=(0, 14))

        # 4. Hardware Fingerprint (Read-only)
        fp_frame = tk.Frame(form, bg=BG_CARD_LIGHT, highlightbackground=BORDER_COLOR, highlightthickness=1)
        fp_frame.pack(fill="x", pady=(0, 16), padx=2)
        tk.Label(fp_frame, text="Node ID:", font=FONT_BODY_BOLD, fg=TEXT_MUTED, bg=BG_CARD_LIGHT).pack(side="left", padx=10, pady=8)
        tk.Label(fp_frame, text=config.node_id, font=FONT_MONO, fg=ACCENT_CYAN, bg=BG_CARD_LIGHT).pack(side="left", pady=8)
        tk.Label(fp_frame, text=f"(FP: {auth_client.fingerprint[:12]}...)", font=FONT_MONO, fg=TEXT_MUTED, bg=BG_CARD_LIGHT).pack(side="left", padx=8, pady=8)

        # Buttons Frame
        btn_frame = tk.Frame(form, bg=BG_CARD)
        btn_frame.pack(fill="x", pady=6)

        pair_btn = tk.Button(
            btn_frame,
            text="⚡ Authenticate & Pair Node",
            font=FONT_BODY_BOLD,
            fg="#101112",
            bg=ACCENT_LIME,
            activebackground="#b3e038",
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            command=self.pair_node,
        )
        pair_btn.pack(side="left", padx=(0, 10))

        test_btn = tk.Button(
            btn_frame,
            text="📡 Test Platform Reachability",
            font=FONT_BODY_BOLD,
            fg=TEXT_PRIMARY,
            bg=BG_CARD_LIGHT,
            activebackground="#2a3241",
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            command=self.test_connection,
        )
        test_btn.pack(side="left")

        # Feedback label
        self.status_lbl = tk.Label(form, text="", font=FONT_BODY, bg=BG_CARD, wraplength=450, justify="left")
        self.status_lbl.pack(anchor="w", pady=10)

    def pair_node(self):
        url = self.url_entry.get().strip()
        token = self.token_entry.get().strip()
        rental = self.rental_entry.get().strip()

        if not token:
            self.status_lbl.config(text="⚠️ Please enter a Pairing Token from your Productify account.", fg=ACCENT_AMBER)
            return

        self.status_lbl.config(text="Authenticating with Productify Cloud...", fg=TEXT_MUTED)
        self.update()

        res = auth_client.pair_with_token(token, rental_id=rental, platform_url=url)
        if res.get("ok"):
            self.status_lbl.config(text="✓ Node successfully paired with Productify platform!", fg=ACCENT_GREEN)
            node_state.log(f"System paired successfully with token '{token[:6]}...'", "INFO")
        else:
            self.status_lbl.config(text=f"Authentication note: {res.get('error')}", fg=ACCENT_RED)

    def test_connection(self):
        url = self.url_entry.get().strip()
        self.status_lbl.config(text=f"Pinging {url}...", fg=TEXT_MUTED)
        self.update()

        res = auth_client.test_platform_connection(url)
        if res.get("reachable"):
            self.status_lbl.config(text=f"✓ Platform is reachable! (HTTP status: {res.get('status_code')})", fg=ACCENT_GREEN)
        else:
            self.status_lbl.config(text=f"❌ Unable to reach platform: {res.get('error')}", fg=ACCENT_RED)
