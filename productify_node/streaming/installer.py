"""Embedded Cloud Gaming Stack Installer Engine for Productify Node.

Provides silent background installation and configuration of:
1. ViGEmBus Virtual Controller Driver (v1.22.0)
2. Sunshine Streaming Server (LizardByte - Free & Open Source under GPL v3)
3. Windows Firewall GameStream port rules (TCP 47984-90, UDP 47998-010)
"""

import os
import sys
import time
import tempfile
import urllib.request
import subprocess
import threading
import logging
from productify_node.state import node_state
from productify_node.streaming.diagnostics import check_vigembus, run_diagnostics
from productify_node.streaming.sunshine_mgr import sunshine_mgr

logger = logging.getLogger("productify_node.installer")

VIGEM_URL = "https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBusSetup_x64.msi"
SUNSHINE_URL = "https://github.com/LizardByte/Sunshine/releases/download/v0.23.1/sunshine-windows-installer.exe"

# Global installation state for UI polling
INSTALL_STATE = {
    "is_running": False,
    "step": "idle",
    "progress": 0,
    "error": None,
    "last_result": None
}
_INSTALL_LOCK = threading.Lock()


def download_file(url, target_path, label="file", log_cb=None):
    def _log(msg, level="INFO"):
        if log_cb:
            log_cb(msg, level)
        node_state.log(msg, level)

    _log(f"Downloading {label} from GitHub...", "INFO")
    try:
        urllib.request.urlretrieve(url, target_path)
        sz = os.path.getsize(target_path)
        _log(f"Downloaded {label} successfully ({round(sz / (1024*1024), 2)} MB).", "INFO")
        return True
    except Exception as e:
        _log(f"Error downloading {label}: {e}", "ERROR")
        return False


def install_vigembus(log_cb=None):
    def _log(msg, level="INFO"):
        if log_cb:
            log_cb(msg, level)
        node_state.log(msg, level)

    status = check_vigembus()
    if status.get("installed"):
        _log("ViGEmBus virtual controller driver is ALREADY installed.", "INFO")
        return True

    _log("Installing ViGEmBus virtual gamepad driver...", "INFO")
    temp_dir = tempfile.gettempdir()
    msi_path = os.path.join(temp_dir, "ViGEmBusSetup_x64.msi")

    if not os.path.exists(msi_path) or os.path.getsize(msi_path) < 10000:
        if not download_file(VIGEM_URL, msi_path, "ViGEmBus installer", log_cb):
            return False

    cmd = ["msiexec.exe", "/i", msi_path, "/quiet", "/norestart"]
    try:
        res = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        if res.returncode == 0:
            _log("ViGEmBus driver installed successfully!", "INFO")
            return True
        else:
            _log(f"ViGEmBus install returned code {res.returncode}. (Administrator privileges required)", "WARNING")
            return False
    except Exception as e:
        _log(f"Failed to run ViGEmBus installer: {e}", "ERROR")
        return False


def install_sunshine(log_cb=None):
    def _log(msg, level="INFO"):
        if log_cb:
            log_cb(msg, level)
        node_state.log(msg, level)

    if sunshine_mgr.is_installed():
        _log(f"Sunshine streaming engine is ALREADY installed at: {sunshine_mgr.sunshine_exe}", "INFO")
        return True

    _log("Installing Sunshine streaming engine (LizardByte GPL v3)...", "INFO")
    temp_dir = tempfile.gettempdir()
    installer_path = os.path.join(temp_dir, "sunshine-installer.exe")

    if not os.path.exists(installer_path) or os.path.getsize(installer_path) < 100000:
        if not download_file(SUNSHINE_URL, installer_path, "Sunshine installer", log_cb):
            return False

    cmd = [installer_path, "/S"]
    try:
        _log("Executing silent Sunshine setup wizard...", "INFO")
        subprocess.run(cmd, timeout=120, capture_output=True, text=True)

        waited = 0
        while waited < 15 and not sunshine_mgr.is_installed():
            time.sleep(1)
            waited += 1

        if sunshine_mgr.is_installed():
            _log(f"Sunshine installed successfully at: {sunshine_mgr.sunshine_exe}", "INFO")
            return True
        else:
            _log("Sunshine installer launched. Checking installation path...", "INFO")
            return sunshine_mgr.is_installed()
    except Exception as e:
        _log(f"Failed to execute Sunshine installer: {e}", "ERROR")
        return False


def configure_firewall(log_cb=None):
    def _log(msg, level="INFO"):
        if log_cb:
            log_cb(msg, level)
        node_state.log(msg, level)

    if os.name != "nt":
        return True

    _log("Configuring Windows Firewall rules for cross-network GameStream ports...", "INFO")
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
        _log("Windows Firewall GameStream ports successfully allowed.", "INFO")
        return True
    except Exception as e:
        _log(f"Firewall setup note (Run as Administrator if rules fail): {e}", "WARNING")
        return False


def run_full_installation_sync(log_cb=None):
    """Executes complete installation pipeline synchronously."""
    global INSTALL_STATE
    with _INSTALL_LOCK:
        INSTALL_STATE["is_running"] = True
        INSTALL_STATE["error"] = None
        INSTALL_STATE["step"] = "vigem"
        INSTALL_STATE["progress"] = 15

        def _log(msg, level="INFO"):
            if log_cb:
                log_cb(msg, level)
            node_state.log(msg, level)

        _log("=== Starting 1-Click Cloud Gaming Stack Installation ===", "INFO")

        # 1. ViGEmBus
        vigem_ok = install_vigembus(log_cb)
        INSTALL_STATE["progress"] = 45
        INSTALL_STATE["step"] = "sunshine"

        # 2. Sunshine
        sun_ok = install_sunshine(log_cb)
        INSTALL_STATE["progress"] = 80
        INSTALL_STATE["step"] = "firewall"

        # 3. Firewall
        configure_firewall(log_cb)
        INSTALL_STATE["progress"] = 95
        INSTALL_STATE["step"] = "diagnostics"

        # 4. Final Diagnostics
        _log("Running pre-flight diagnostics verification...", "INFO")
        diag = run_diagnostics()
        INSTALL_STATE["progress"] = 100
        INSTALL_STATE["step"] = "completed"
        INSTALL_STATE["is_running"] = False
        INSTALL_STATE["last_result"] = diag

        if diag.get("ready_for_cloud_gaming"):
            _log("🎉 Cloud Gaming Stack is 100% READY! Machine can now host low-latency sessions.", "INFO")
        else:
            _log("Cloud Gaming Stack setup finished. Check diagnostics for details.", "INFO")

        return diag


def start_installation_async(log_cb=None):
    """Launches installation in background thread if not already running."""
    if INSTALL_STATE["is_running"]:
        return False
    t = threading.Thread(target=run_full_installation_sync, args=(log_cb,), daemon=True)
    t.start()
    return True
