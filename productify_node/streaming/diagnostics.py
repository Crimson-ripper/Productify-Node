"""Host gaming stack diagnostics & hardware pre-flight checker."""

import os
import sys
import socket
import logging
from productify_node.telemetry import probe_gpu
from productify_node.streaming.sunshine_mgr import sunshine_mgr, get_public_ip

logger = logging.getLogger("productify_node.diagnostics")


def check_vigembus():
    """Verify if ViGEmBus virtual gamepad driver is installed on Windows."""
    if os.name != "nt":
        return {"installed": False, "reason": "Non-Windows OS (ViGEmBus not required on Linux)"}

    sys_driver = os.path.expandvars(r"%SYSTEMROOT%\System32\drivers\ViGEmBus.sys")
    if os.path.exists(sys_driver):
        return {"installed": True, "path": sys_driver}

    # Alternative check via sc query
    try:
        import subprocess
        res = subprocess.run(["sc", "query", "ViGEmBus"], capture_output=True, text=True, timeout=3)
        if "RUNNING" in res.stdout or "STOPPED" in res.stdout:
            return {"installed": True, "service": "ViGEmBus"}
    except Exception:
        pass

    return {
        "installed": False,
        "reason": "ViGEmBus driver not found. Run scripts/install_gaming_stack.bat to install.",
        "download_url": "https://github.com/nefarius/ViGEmBus/releases/latest"
    }


def check_port_availability(ports=None):
    """Verify if streaming ports are open and not blocked by local applications."""
    if ports is None:
        ports = [47989, 47990, 47998]
    report = {}
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(0.5)
            s.bind(("0.0.0.0", p))
            report[p] = True
        except Exception:
            report[p] = False
        finally:
            s.close()
    return report


def run_diagnostics():
    """Run comprehensive check of host streaming capabilities."""
    gpu_info = probe_gpu()
    gpu_name = gpu_info.get("name", "Unknown GPU")
    has_nvidia = gpu_info.get("available", False) or any(
        k in gpu_name.lower() for k in ["nvidia", "geforce", "rtx", "gtx"]
    )
    vram_mb = gpu_info.get("vram_total_mb", 0)
    vram_str = f"{vram_mb:.0f} MB" if vram_mb > 0 else "N/A"
    driver_str = gpu_info.get("driver_version", "N/A")

    sunshine_installed = sunshine_mgr.is_installed()
    vigem_status = check_vigembus()
    port_status = check_port_availability([47989, 47990, 47998])
    wan_ip = get_public_ip()

    ready = (has_nvidia or gpu_name != "No NVIDIA GPU Detected") and sunshine_installed and vigem_status.get("installed", False)

    return {
        "ready_for_cloud_gaming": ready,
        "gpu": {
            "name": gpu_name,
            "vram": vram_str,
            "driver": driver_str,
            "nvenc_capable": has_nvidia,
        },
        "sunshine": {
            "installed": sunshine_installed,
            "path": sunshine_mgr.sunshine_exe,
        },
        "vigembus_controller_driver": vigem_status,
        "ports_available": port_status,
        "network": {
            "public_wan_ip": wan_ip,
            "cross_network_ready": bool(wan_ip and wan_ip != "127.0.0.1")
        }
    }


def print_diagnostic_report():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    diag = run_diagnostics()
    print("=" * 65)
    print("⚡ PRODUCTIFY NODE — CLOUD GAMING HOST PRE-FLIGHT DIAGNOSTICS")
    print("=" * 65)
    print(f"Host GPU            : {diag['gpu']['name']} ({diag['gpu']['vram']})")
    print(f"NVENC Hardware Enc  : {'✅ Supported' if diag['gpu']['nvenc_capable'] else '⚠️ Software fallback / Non-NVIDIA'}")
    print(f"Sunshine Engine     : {'✅ Installed (' + str(diag['sunshine']['path']) + ')' if diag['sunshine']['installed'] else '❌ Missing (Run scripts/install_gaming_stack.bat)'}")
    print(f"ViGEmBus Controller : {'✅ Installed' if diag['vigembus_controller_driver']['installed'] else '❌ Missing (Run scripts/install_gaming_stack.bat)'}")
    print(f"Public WAN IP       : {diag['network']['public_wan_ip']} (Cross-network streaming)")
    print(f"Ports (47989/47990) : {'✅ Ready' if all(diag['ports_available'].values()) else '⚠️ Some ports occupied'}")
    print("-" * 65)
    if diag["ready_for_cloud_gaming"]:
        print("🟢 STATUS: 100% READY TO HOST CLOUD GAMING SESSIONS!")
    else:
        print("🟡 STATUS: ACTION REQUIRED — Please run scripts/install_gaming_stack.bat")
    print("=" * 65)


if __name__ == "__main__":
    print_diagnostic_report()
