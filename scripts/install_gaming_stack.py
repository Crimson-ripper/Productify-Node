#!/usr/bin/env python3
"""Automated 1-Click Dependency Installer for Productify Cloud Gaming Host Node.

Installs and configures:
  1. Sunshine Streaming Server (LizardByte - Free & Open Source under GPL v3)
  2. ViGEmBus Virtual Gamepad Driver (for low-latency remote Xbox 360 controller emulation)
  3. Windows Firewall Rules for GameStream ports (TCP 47984-47990, UDP 47998-48010)
  4. Runs full diagnostic verification

Usage:
  py scripts/install_gaming_stack.py          # Full automatic download & install
  py scripts/install_gaming_stack.py --check  # Check status only (no install)
"""

import os
import sys
import shutil
import urllib.request
import subprocess
import argparse
import tempfile

VIGEM_URL = "https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBusSetup_x64.msi"
SUNSHINE_URL = "https://github.com/LizardByte/Sunshine/releases/download/v0.23.1/sunshine-windows-installer.exe"

BIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "sunshine"))


def run_cmd(cmd, check=True):
    print(f"[*] Executing: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def download_file(url, target_path, label="file"):
    print(f"[*] Downloading {label} from {url}...")
    try:
        urllib.request.urlretrieve(url, target_path)
        print(f"[+] Downloaded {label} successfully ({os.path.getsize(target_path)} bytes).")
        return True
    except Exception as e:
        print(f"[!] Error downloading {label}: {e}")
        return False


def install_vigembus():
    from productify_node.streaming.diagnostics import check_vigembus
    status = check_vigembus()
    if status.get("installed"):
        print("[+] ViGEmBus virtual controller driver is ALREADY installed.")
        return True

    print("[*] Installing ViGEmBus virtual gamepad driver...")
    temp_dir = tempfile.gettempdir()
    msi_path = os.path.join(temp_dir, "ViGEmBusSetup_x64.msi")

    if not os.path.exists(msi_path) or os.path.getsize(msi_path) < 10000:
        ok = download_file(VIGEM_URL, msi_path, "ViGEmBus installer")
        if not ok:
            return False

    cmd = ["msiexec.exe", "/i", msi_path, "/quiet", "/norestart"]
    try:
        res = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        if res.returncode == 0:
            print("[+] ViGEmBus driver installed successfully!")
            return True
        else:
            print(f"[!] ViGEmBus install returned code {res.returncode}. (Run with admin privileges if needed)")
            return False
    except Exception as e:
        print(f"[!] Failed to run ViGEmBus installer: {e}")
        return False


def install_sunshine():
    from productify_node.streaming.sunshine_mgr import sunshine_mgr
    if sunshine_mgr.is_installed():
        print(f"[+] Sunshine streaming engine is ALREADY installed at: {sunshine_mgr.sunshine_exe}")
        return True

    print("[*] Installing Sunshine streaming engine (LizardByte FLOSS)...")
    temp_dir = tempfile.gettempdir()
    installer_path = os.path.join(temp_dir, "sunshine-installer.exe")

    if not os.path.exists(installer_path) or os.path.getsize(installer_path) < 100000:
        ok = download_file(SUNSHINE_URL, installer_path, "Sunshine installer")
        if not ok:
            return False

    # Run silent / non-interactive install if supported
    cmd = [installer_path, "/S"]
    try:
        print("[*] Running Sunshine installer...")
        res = subprocess.run(cmd, timeout=120, capture_output=True, text=True)
        time_waited = 0
        while time_waited < 15 and not sunshine_mgr.is_installed():
            import time
            time.sleep(1)
            time_waited += 1

        if sunshine_mgr.is_installed():
            print(f"[+] Sunshine installed successfully at: {sunshine_mgr.sunshine_exe}")
            return True
        else:
            print("[*] Sunshine installer launched. Please finish the wizard on screen.")
            return True
    except Exception as e:
        print(f"[!] Failed to run Sunshine installer: {e}")
        return False


def configure_firewall():
    if os.name != "nt":
        return

    print("[*] Adding Windows Firewall rules for cross-network GameStream ports...")
    try:
        # TCP Ports: 47984, 47989, 47990
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             "name=Productify-Sunshine-TCP", "dir=in", "action=allow", "protocol=TCP", "localport=47984,47989,47990"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # UDP Ports: 47998, 47999, 48000, 48002, 48010
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             "name=Productify-Sunshine-UDP", "dir=in", "action=allow", "protocol=UDP", "localport=47998,47999,48000,48002,48010"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print("[+] Firewall rules for Sunshine streaming added.")
    except Exception as e:
        print(f"[!] Note: Could not configure firewall automatically (Requires Admin): {e}")


def main():
    parser = argparse.ArgumentParser(description="Automated Cloud Gaming Host Package Installer")
    parser.add_argument("--check", action="store_true", help="Run diagnostics check only without installing")
    args = parser.parse_args()

    print("=" * 65)
    print("⚡ PRODUCTIFY NODE — CLOUD GAMING STACK INSTALLER")
    print("=" * 65)

    if args.check:
        from productify_node.streaming.diagnostics import print_diagnostic_report
        print_diagnostic_report()
        return

    if not is_admin():
        print("[!] NOTICE: For automated driver installation and firewall setup,")
        print("    running this script as Administrator is strongly recommended.")
        print("-" * 65)

    # 1. Install ViGEmBus
    install_vigembus()

    # 2. Install Sunshine
    install_sunshine()

    # 3. Configure Firewall
    configure_firewall()

    # 4. Run Diagnostics Report
    print("\n[*] Running final pre-flight verification...")
    from productify_node.streaming.diagnostics import print_diagnostic_report
    print_diagnostic_report()


if __name__ == "__main__":
    main()
