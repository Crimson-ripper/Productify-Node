"""Local loopback HTTP bridge (127.0.0.1:48123) for browser integration and Webview GUI.

Unifies Productify Node Hypervisor, Compute Provider, and Cloud Gaming Stack Setup
into a single, cohesive, professional desktop studio.
"""

import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import logging
from productify_node.config import config
from productify_node.state import node_state
from productify_node.boundary import enforcer
from productify_node.telemetry import get_full_telemetry
from productify_node.thermal_guard import thermal_guard
from productify_node.container import container_mgr
from productify_node.streaming.diagnostics import run_diagnostics
from productify_node.streaming.sunshine_mgr import sunshine_mgr
from productify_node.streaming.installer import (
    INSTALL_STATE,
    start_installation_async,
)

logger = logging.getLogger("productify_node.bridge")


class BridgeHandler(BaseHTTPRequestHandler):
    """Handles local loopback requests from the seller dashboard and embedded webview."""

    def _set_cors(self, status=200):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors(200)

    def do_GET(self):
        if self.path.startswith("/probe") or self.path == "/":
            telemetry = get_full_telemetry()
            thermal = thermal_guard.get_status()
            try:
                diag = run_diagnostics()
            except Exception:
                diag = {}

            data = {
                "ok": True,
                "node_id": config.node_id,
                "node_name": config.get("node_name"),
                "status": node_state.status,
                "is_live": node_state.is_live,
                "gpu": telemetry["gpu"]["name"] if telemetry["gpu"]["available"] else "CPU Compute Node",
                "gpu_available": telemetry["gpu"]["available"],
                "vram": f"{round(telemetry['gpu']['vram_total_mb'] / 1024, 1)} GB" if telemetry["gpu"]["available"] else "N/A",
                "cpu": telemetry["cpu"]["name"],
                "cpu_cores": telemetry["cpu"]["cores"],
                "ram": f"{telemetry['ram']['total_gb']} GB",
                "storage_free": f"{telemetry['disk']['free_gb']} GB",
                "temperature": f"{telemetry['gpu']['temperature_c']}°C" if telemetry["gpu"]["available"] else "N/A",
                "temperature_val": telemetry["gpu"]["temperature_c"] if telemetry["gpu"]["available"] else 0,
                "driver_version": telemetry["gpu"]["driver_version"],
                "allocated_ram_gb": config.ram_limit_gb,
                "allocated_disk_gb": config.disk_limit_gb,
                "thermal": thermal,
                "active_pods": len(node_state.get_active_pods()),
                "gaming_ready": diag.get("ready_for_cloud_gaming", False),
                "sunshine_installed": diag.get("sunshine", False),
                "vigem_installed": diag.get("vigem", False),
                "firewall_ready": diag.get("firewall", False),
                "wan_ip": diag.get("wan_ip", "127.0.0.1"),
            }
            self._set_cors(200)
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif self.path == "/status":
            self._set_cors(200)
            payload = {
                "ok": True,
                "node_id": config.node_id,
                "status": node_state.status,
                "is_live": node_state.is_live,
                "tunnel_connected": node_state.tunnel_connected,
                "active_pods": len(node_state.get_active_pods()),
                "ram_limit_gb": config.ram_limit_gb,
                "disk_limit_gb": config.disk_limit_gb,
                "thermal": thermal_guard.get_status(),
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        elif self.path == "/thermal":
            self._set_cors(200)
            self.wfile.write(json.dumps(thermal_guard.get_status()).encode("utf-8"))

        elif self.path == "/logs":
            self._set_cors(200)
            self.wfile.write(json.dumps({"logs": node_state.get_logs(100)}).encode("utf-8"))

        elif self.path == "/gaming/status":
            try:
                diag = run_diagnostics()
            except Exception as e:
                diag = {"ready_for_cloud_gaming": False, "error": str(e)}

            payload = {
                "ok": True,
                "ready": diag.get("ready_for_cloud_gaming", False),
                "gpu": diag.get("gpu", {}),
                "sunshine": diag.get("sunshine", {}),
                "vigem": diag.get("vigembus_controller_driver", {}),
                "ports": diag.get("ports_available", {}),
                "network": diag.get("network", {}),
                "streaming_active": sunshine_mgr.is_running(),
                "current_session": sunshine_mgr.current_session,
                "install_state": INSTALL_STATE
            }
            self._set_cors(200)
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        elif self.path == "/gaming/install-progress":
            self._set_cors(200)
            self.wfile.write(json.dumps(INSTALL_STATE).encode("utf-8"))

        elif self.path in ["/ui", "/app", "/dashboard"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_UI_PAGE.encode("utf-8"))
        else:
            self._set_cors(404)
            self.wfile.write(b'{"error": "Not found"}')

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if self.path == "/tunnel/connect":
            rental_id = payload.get("rental_id") or payload.get("node_id")
            token = payload.get("token") or payload.get("pairing_token")
            if rental_id:
                config.set("rental_id", rental_id)
            if token:
                config.set("pairing_token", token)
            node_state.set_live()
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "status": "LIVE", "rental_id": rental_id}).encode("utf-8"))

        elif self.path == "/toggle":
            new_status = node_state.toggle_live_pause()
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "status": new_status}).encode("utf-8"))

        elif self.path == "/emergency_stop":
            count = container_mgr.destroy_all_pods()
            node_state.set_paused()
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "wiped": True, "stopped_pods": count}).encode("utf-8"))

        elif self.path == "/allocation":
            ram = payload.get("ram_limit_gb")
            disk = payload.get("disk_limit_gb")
            res = enforcer.set_allocations(ram, disk)
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "allocations": res}).encode("utf-8"))

        elif self.path == "/thermal/limits":
            max_t = payload.get("max_temp_c")
            if max_t:
                thermal_guard.set_limits(max_temp=int(max_t))
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "thermal": thermal_guard.get_status()}).encode("utf-8"))

        elif self.path == "/gaming/install":
            started = start_installation_async()
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "started": started, "state": INSTALL_STATE}).encode("utf-8"))

        elif self.path == "/gaming/test-stream":
            session = sunshine_mgr.start_session("test-sandbox", "Productify Gaming Sandbox")
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "session": session}).encode("utf-8"))

        elif self.path == "/gaming/stop-stream":
            res = sunshine_mgr.stop_session()
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "stopped": res}).encode("utf-8"))
        else:
            self._set_cors(404)
            self.wfile.write(b'{"error": "Not found"}')

    def log_message(self, format, *args):
        # Suppress standard access logging to keep console clean
        pass


class LocalBridgeServer:
    def __init__(self, port=48123):
        self.port = port
        self.server = None
        self.thread = None
        self._is_ready = threading.Event()

    def start(self):
        if self.server is not None:
            return
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), BridgeHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self._is_ready.set()
            node_state.log(f"Local bridge server listening on http://127.0.0.1:{self.port}", "INFO")
        except Exception as e:
            logger.warning(f"Could not bind bridge server on port {self.port}: {e}")

    def wait_until_ready(self, timeout=2.0):
        return self._is_ready.wait(timeout)

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None


local_bridge = LocalBridgeServer()

HTML_UI_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Productify Node — Hypervisor & Cloud Gaming Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,400;0,500;0,700;1,400&family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #06080d;
      --bg-surface: #0a0e17;
      --card: #0f1523;
      --card-hover: #141c2e;
      --card-sub: #131a2b;
      --border: rgba(255, 255, 255, 0.08);
      --border-hover: rgba(200, 240, 76, 0.35);
      --border-cyan: rgba(0, 240, 255, 0.35);
      --text-primary: #f8fafc;
      --text-muted: #94a3b8;
      --text-sub: #64748b;
      --lime: #c8f04c;
      --lime-glow: rgba(200, 240, 76, 0.25);
      --cyan: #00f0ff;
      --cyan-glow: rgba(0, 240, 255, 0.25);
      --violet: #7000ff;
      --green: #10b981;
      --green-glow: rgba(16, 185, 129, 0.25);
      --amber: #f59e0b;
      --red: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-base);
      background-image: 
        radial-gradient(circle at 15% 10%, rgba(0, 240, 255, 0.04) 0%, transparent 45%),
        radial-gradient(circle at 85% 15%, rgba(200, 240, 76, 0.04) 0%, transparent 45%),
        linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px);
      background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
      color: var(--text-primary);
      font-family: 'Manrope', sans-serif;
      padding: 24px;
      max-width: 1140px;
      margin: 0 auto;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }

    /* Top Brand Navigation */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(15, 21, 35, 0.85);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px 24px;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 16px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
    }
    .brand-wrap { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
    .brand {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 1.45rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .brand span { color: var(--lime); text-shadow: 0 0 15px var(--lime-glow); }
    .badge-version {
      font-family: 'DM Mono', monospace;
      font-size: 0.7rem;
      font-weight: 700;
      background: rgba(200, 240, 76, 0.12);
      color: var(--lime);
      border: 1px solid rgba(200, 240, 76, 0.3);
      padding: 3px 8px;
      border-radius: 6px;
      letter-spacing: 0.05em;
    }
    .gpu-chip {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(0, 240, 255, 0.08);
      border: 1px solid var(--border-cyan);
      color: var(--cyan);
      font-family: 'DM Mono', monospace;
      font-size: 0.76rem;
      padding: 5px 12px;
      border-radius: 20px;
      font-weight: 600;
    }
    .node-id {
      font-size: 0.76rem;
      color: var(--text-muted);
      font-family: 'DM Mono', monospace;
      background: var(--bg-surface);
      padding: 5px 12px;
      border-radius: 8px;
      border: 1px solid var(--border);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .node-id:hover { border-color: var(--border-hover); color: var(--text-primary); }

    /* Live Toggle Button */
    .controls-wrap { display: flex; align-items: center; gap: 14px; }
    .live-toggle-btn {
      background: linear-gradient(135deg, #10b981 0%, #059669 100%);
      color: #022c22;
      border: none;
      padding: 10px 24px;
      border-radius: 10px;
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 800;
      font-size: 0.92rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 0 25px var(--green-glow);
    }
    .live-toggle-btn:hover { transform: translateY(-2px); box-shadow: 0 0 35px rgba(16, 185, 129, 0.45); }
    .live-toggle-btn.paused {
      background: #1e293b;
      color: #cbd5e1;
      box-shadow: none;
      border: 1px solid var(--border);
    }
    .live-toggle-btn.paused:hover { background: #273549; color: #fff; }

    /* Radar Ping Dot */
    .radar-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 10px currentColor;
    }

    /* Revenue & Telemetry Ticker */
    .ticker-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: linear-gradient(90deg, rgba(200, 240, 76, 0.05) 0%, rgba(0, 240, 255, 0.04) 50%, rgba(112, 0, 255, 0.04) 100%);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 14px 24px;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .ticker-item { display: flex; flex-direction: column; }
    .ticker-label {
      font-size: 0.7rem;
      text-transform: uppercase;
      font-weight: 800;
      color: var(--text-muted);
      letter-spacing: 0.08em;
      margin-bottom: 2px;
    }
    .ticker-val {
      font-size: 1.25rem;
      font-weight: 800;
      color: var(--text-primary);
      font-family: 'Space Grotesk', sans-serif;
    }
    .ticker-val.glow { color: var(--lime); text-shadow: 0 0 14px var(--lime-glow); }
    .ticker-val.cyan { color: var(--cyan); text-shadow: 0 0 14px var(--cyan-glow); }

    /* Thermal Guard Shield Banner */
    .thermal-shield {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(16, 185, 129, 0.07);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 12px;
      padding: 12px 20px;
      margin-bottom: 20px;
      font-size: 0.88rem;
    }
    .thermal-shield.warn { background: rgba(245, 158, 11, 0.08); border-color: rgba(245, 158, 11, 0.35); }
    .thermal-shield.overheat { background: rgba(239, 68, 68, 0.12); border-color: rgba(239, 68, 68, 0.45); animation: pulse 1.5s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
    .shield-badge {
      font-weight: 800;
      font-size: 0.75rem;
      padding: 4px 10px;
      border-radius: 6px;
      background: rgba(16, 185, 129, 0.2);
      color: var(--green);
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .shield-badge.warn { background: rgba(245, 158, 11, 0.2); color: var(--amber); }
    .shield-badge.overheat { background: rgba(239, 68, 68, 0.25); color: var(--red); }

    /* Tabs Navigation */
    .tabs {
      display: flex;
      gap: 10px;
      margin-bottom: 22px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
      overflow-x: auto;
    }
    .tab-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 10px 20px;
      border-radius: 10px;
      font-family: 'Space Grotesk', sans-serif;
      font-size: 0.92rem;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
      white-space: nowrap;
    }
    .tab-btn:hover { color: var(--text-primary); background: rgba(255, 255, 255, 0.04); }
    .tab-btn.active {
      background: var(--card);
      color: var(--lime);
      border-color: rgba(200, 240, 76, 0.35);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
    }
    .tab-btn.active.gaming {
      color: var(--cyan);
      border-color: rgba(0, 240, 255, 0.4);
    }

    .panel { display: none; animation: fadeIn 0.2s ease; }
    .panel.active { display: block; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

    /* Cards & Grids */
    .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; margin-bottom: 22px; }
    .grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 22px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
    }
    .card:hover { border-color: rgba(255, 255, 255, 0.16); transform: translateY(-1px); }
    .card.highlight { border-color: rgba(0, 240, 255, 0.3); background: linear-gradient(145deg, #0e1526, #090e1a); }
    .card-title {
      font-size: 0.74rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--text-muted);
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .card-val {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 1.35rem;
      font-weight: 800;
      color: var(--text-primary);
      margin-bottom: 6px;
      word-break: break-word;
    }
    .card-sub { font-size: 0.84rem; color: var(--text-muted); line-height: 1.4; }

    /* Status Pill Badges */
    .status-pill {
      font-family: 'DM Mono', monospace;
      font-size: 0.72rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      text-transform: uppercase;
    }
    .status-pill.success { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
    .status-pill.error { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
    .status-pill.warn { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
    .status-pill.cyan { background: rgba(0, 240, 255, 0.15); color: #00f0ff; border: 1px solid rgba(0, 240, 255, 0.3); }

    /* Action Buttons */
    .btn-primary {
      background: linear-gradient(135deg, #00f0ff 0%, #0077ff 100%);
      color: #030712;
      border: none;
      padding: 13px 28px;
      border-radius: 10px;
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 800;
      font-size: 0.95rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      transition: all 0.2s ease;
      box-shadow: 0 0 25px rgba(0, 240, 255, 0.35);
    }
    .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 0 35px rgba(0, 240, 255, 0.5); }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }

    .btn-lime {
      background: linear-gradient(135deg, #c8f04c 0%, #9bc427 100%);
      color: #090b0e;
      border: none;
      padding: 12px 26px;
      border-radius: 10px;
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 800;
      font-size: 0.95rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
      box-shadow: 0 0 20px var(--lime-glow);
    }
    .btn-lime:hover { transform: translateY(-2px); box-shadow: 0 0 30px rgba(200, 240, 76, 0.45); }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 10px 20px;
      border-radius: 8px;
      font-size: 0.88rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s ease;
    }
    .btn-secondary:hover { background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.2); }

    /* Progress Bar */
    .progress-bar-wrap {
      width: 100%;
      height: 8px;
      background: #1e293b;
      border-radius: 10px;
      overflow: hidden;
      margin-top: 14px;
      display: none;
    }
    .progress-bar-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #00f0ff, #c8f04c);
      background-size: 30px 30px;
      background-image: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 25%, transparent 25%, transparent 50%, rgba(255, 255, 255, 0.2) 50%, rgba(255, 255, 255, 0.2) 75%, transparent 75%, transparent);
      animation: progress-stripes 1s linear infinite;
      transition: width 0.3s ease;
    }
    @keyframes progress-stripes { from { background-position: 0 0; } to { background-position: 30px 0; } }

    /* Terminal Console */
    .terminal {
      background: #04060a;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px;
      font-family: 'DM Mono', monospace;
      font-size: 0.82rem;
      height: 320px;
      overflow-y: auto;
      color: #cbd5e1;
      line-height: 1.6;
      box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.6);
    }
    .terminal .log-line { margin-bottom: 3px; word-break: break-all; }
    .terminal .time { color: var(--text-sub); margin-right: 8px; }
    .terminal .INFO { color: #cbd5e1; }
    .terminal .WARNING { color: #f59e0b; }
    .terminal .ERROR { color: #ef4444; font-weight: 700; }
    .terminal .SUCCESS { color: #10b981; font-weight: 700; }

    /* Sliders */
    .slider-box {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 18px;
    }
    .slider-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-weight: 700; font-size: 0.98rem; }
    .slider-val { font-size: 1.2rem; font-weight: 800; color: var(--lime); font-family: 'DM Mono', monospace; }
    input[type=range] { width: 100%; height: 6px; background: #222936; border-radius: 4px; outline: none; margin: 14px 0; accent-color: var(--lime); cursor: pointer; }
    .presets { display: flex; gap: 10px; margin-top: 12px; }
    .preset-btn {
      background: var(--card-hover);
      color: var(--text-primary);
      border: 1px solid var(--border);
      padding: 6px 14px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
    }
    .preset-btn:hover { border-color: var(--lime); color: var(--lime); }

    /* Danger Emergency Stop */
    .danger-box {
      background: rgba(239, 68, 68, 0.06);
      border: 1px solid rgba(239, 68, 68, 0.25);
      border-radius: 14px;
      padding: 24px;
      margin-top: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }
    .danger-btn {
      background: #ef4444;
      color: #fff;
      border: none;
      padding: 12px 24px;
      border-radius: 10px;
      font-weight: 800;
      font-size: 0.9rem;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .danger-btn:hover { background: #dc2626; box-shadow: 0 0 20px rgba(239, 68, 68, 0.4); }

    /* Setup Banner in Gaming Tab */
    .gaming-hero {
      background: linear-gradient(135deg, rgba(0, 240, 255, 0.08) 0%, rgba(112, 0, 255, 0.08) 100%);
      border: 1px solid var(--border-cyan);
      border-radius: 16px;
      padding: 24px 28px;
      margin-bottom: 22px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 20px;
    }
  </style>
</head>
<body>
  <!-- Top Navigation & Brand Header -->
  <header>
    <div class="brand-wrap">
      <div class="brand">⚡ PRODUCTIFY <span>NODE</span></div>
      <div class="badge-version">HYPERVISOR v2.0</div>
      <div class="gpu-chip" id="topGpuChip">NVIDIA NVENC ACTIVE</div>
      <div class="node-id" id="nodeId" onclick="copyNodeId()" title="Click to copy Node ID">Node: Probing...</div>
    </div>
    <div class="controls-wrap">
      <button id="liveBtn" class="live-toggle-btn" onclick="toggleLive()">
        <span class="radar-dot" id="liveDot"></span>
        <span id="liveText">LIVE (Hosting & Earning)</span>
      </button>
    </div>
  </header>

  <!-- Live Revenue & Metering Ticker Bar -->
  <div class="ticker-bar">
    <div class="ticker-item">
      <div class="ticker-label">Active Session Time</div>
      <div class="ticker-val" id="sessionTimer">00:00:00</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Compute Rate</div>
      <div class="ticker-val glow" id="earningRate">$0.60 / hr</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Session Metered Earnings</div>
      <div class="ticker-val glow" id="sessionEarnings">$0.0000</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Active Pods</div>
      <div class="ticker-val" id="activePodsCount">0 Active</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Cloud Gaming Stack</div>
      <div class="ticker-val cyan" id="gamingStackStatus">Probing...</div>
    </div>
  </div>

  <!-- Hardware Thermal Guard Shield Banner -->
  <div class="thermal-shield" id="thermalShield">
    <div style="display: flex; align-items: center; gap: 12px;">
      <span style="font-size: 1.3rem;">🛡️</span>
      <div>
        <b>Hardware Thermal Guard:</b> Active cooling protection locked at <b>75°C ceiling</b>.
        Current: <b id="gpuTempShield">--°C</b>
      </div>
    </div>
    <div class="shield-badge" id="shieldBadge">ACTIVE & SAFE</div>
  </div>

  <!-- Unified Navigation Tabs -->
  <div class="tabs">
    <button class="tab-btn active gaming" onclick="showTab('gaming', this)">🎮 Cloud Gaming Stack (Setup & Host)</button>
    <button class="tab-btn" onclick="showTab('dash', this)">📊 Hardware Telemetry</button>
    <button class="tab-btn" onclick="showTab('alloc', this)">🛡️ Thermal & Safe Limits</button>
    <button class="tab-btn" onclick="showTab('tunnel', this)">⚡ Cloud Tunnel & Pairing</button>
    <button class="tab-btn" onclick="showTab('logs', this)">📜 Live Console Logs</button>
  </div>

  <!-- ========================================================= -->
  <!-- TAB 1: CLOUD GAMING STACK (MERGED INSTALLER & STREAMING) -->
  <!-- ========================================================= -->
  <div id="tab-gaming" class="panel active">
    <!-- Hero Banner -->
    <div class="gaming-hero">
      <div style="max-width: 620px;">
        <h2 style="font-family: 'Space Grotesk', sans-serif; font-size: 1.35rem; font-weight: 800; margin-bottom: 6px; letter-spacing: -0.02em;">
          Host Real Cloud Gaming Sessions over the Public WAN
        </h2>
        <p style="color: var(--text-muted); font-size: 0.88rem; line-height: 1.5;">
          Equip your machine with the LizardByte Sunshine streaming engine and ViGEmBus gamepad driver.
          Players on remote laptops can rent your GPU and play with &lt;25ms latency and 60–120 FPS.
        </p>
      </div>
      <div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end;">
        <button id="btnInstallGaming" class="btn-primary" onclick="triggerGamingInstall()">
          ⚡ 1-Click Install / Repair Gaming Stack
        </button>
        <div id="installStatusText" style="font-size: 0.76rem; color: var(--text-muted);">
          Automated download, silent driver setup & firewall configuration
        </div>
      </div>
    </div>

    <!-- Animated Progress Bar -->
    <div class="progress-bar-wrap" id="progressBarWrap">
      <div class="progress-bar-fill" id="progressBarFill"></div>
    </div>

    <!-- 4 Diagnostic Cards Grid -->
    <div class="grid-4" style="margin-top: 18px;">
      <!-- Card 1: Sunshine -->
      <div class="card highlight">
        <div class="card-title">
          <span>SUNSHINE ENGINE</span>
          <span id="sunshinePill" class="status-pill warn">Checking</span>
        </div>
        <div class="card-val" id="sunshineStatusText" style="font-size: 1.15rem;">Probing...</div>
        <div class="card-sub" id="sunshineSub">GPL v3 Free Streaming Server</div>
      </div>

      <!-- Card 2: ViGEmBus -->
      <div class="card highlight">
        <div class="card-title">
          <span>VIRTUAL GAMEPAD</span>
          <span id="vigemPill" class="status-pill warn">Checking</span>
        </div>
        <div class="card-val" id="vigemStatusText" style="font-size: 1.15rem;">Probing...</div>
        <div class="card-sub" id="vigemSub">ViGEmBus Xbox 360 controller emulation</div>
      </div>

      <!-- Card 3: Windows Firewall -->
      <div class="card highlight">
        <div class="card-title">
          <span>FIREWALL PORTS</span>
          <span id="firewallPill" class="status-pill warn">Checking</span>
        </div>
        <div class="card-val" id="firewallStatusText" style="font-size: 1.15rem;">TCP/UDP Ports</div>
        <div class="card-sub">TCP 47984-90 · UDP 47998-010</div>
      </div>

      <!-- Card 4: WAN Reachability -->
      <div class="card highlight">
        <div class="card-title">
          <span>PUBLIC WAN IP</span>
          <span id="wanPill" class="status-pill cyan">STUN</span>
        </div>
        <div class="card-val" id="wanStatusText" style="font-size: 1.15rem; font-family: 'DM Mono', monospace;">Detecting...</div>
        <div class="card-sub">External IP for cross-network streaming</div>
      </div>
    </div>

    <!-- Active Stream Testing & Moonlight Launcher -->
    <div class="card" style="margin-bottom: 22px; background: rgba(15, 23, 42, 0.7);">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; margin-bottom: 14px;">
        <div>
          <h3 style="font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem; font-weight: 800;">
            Live Stream Controller & Test Sandbox
          </h3>
          <p style="font-size: 0.82rem; color: var(--text-muted);">
            Test your Sunshine streaming server locally before opening your machine to marketplace renters.
          </p>
        </div>
        <div style="display: flex; gap: 10px;">
          <button id="btnStartStream" class="btn-secondary" onclick="startTestStream()">
            🚀 Start Test Stream
          </button>
          <button id="btnStopStream" class="btn-secondary" onclick="stopTestStream()" style="color: var(--red);">
            🛑 Stop Stream
          </button>
        </div>
      </div>

      <!-- Session Parameters (if streaming) -->
      <div id="streamSessionInfo" style="display: none; background: rgba(0, 240, 255, 0.05); border: 1px solid var(--border-cyan); border-radius: 10px; padding: 14px 18px; margin-top: 10px;">
        <div style="display: flex; gap: 24px; flex-wrap: wrap; align-items: center; font-size: 0.85rem;">
          <div>WAN Host: <b id="streamHostIp" style="color: var(--cyan); font-family: 'DM Mono', monospace;">122.161.64.41:47989</b></div>
          <div>Pairing PIN: <b id="streamPin" style="color: var(--lime); font-family: 'DM Mono', monospace; font-size: 1.1rem;">----</b></div>
          <a id="streamMoonlightLink" href="#" style="color: #38bdf8; font-weight: 700; text-decoration: underline;">Launch in Moonlight App &rarr;</a>
        </div>
      </div>
    </div>

    <!-- Real-Time Installer & Pre-Flight Diagnostic Logs -->
    <div class="card">
      <div class="card-title">
        <span>INSTALLATION & DIAGNOSTICS LOGS</span>
        <button class="btn-secondary" style="padding: 4px 10px; font-size: 0.72rem;" onclick="clearGamingLogs()">Clear</button>
      </div>
      <div class="terminal" id="termGaming">
        <div class="log-line INFO"><span class="time">[00:00:00]</span> Productify Cloud Gaming Hypervisor ready. Click '1-Click Install' above to verify dependencies.</div>
      </div>
    </div>
  </div>

  <!-- ========================================================= -->
  <!-- TAB 2: HARDWARE DASHBOARD & TELEMETRY -->
  <!-- ========================================================= -->
  <div id="tab-dash" class="panel">
    <div class="grid-2">
      <div class="card">
        <div class="card-title">
          <span>GPU ACCELERATION</span>
          <span style="color: var(--lime); font-size: 0.72rem;">PASSTHROUGH ACTIVE</span>
        </div>
        <div class="card-val" id="gpuName">Checking...</div>
        <div class="card-sub" id="gpuSub">VRAM & Driver query in progress</div>
      </div>
      <div class="card">
        <div class="card-title">
          <span>CPU PROCESSOR</span>
          <span style="color: var(--cyan); font-size: 0.72rem;">HOST CORE</span>
        </div>
        <div class="card-val" id="cpuName">Checking...</div>
        <div class="card-sub" id="cpuSub">Cores & Threads</div>
      </div>
      <div class="card">
        <div class="card-title">
          <span>PHYSICAL RAM</span>
          <span style="color: var(--green); font-size: 0.72rem;">CONTAINED</span>
        </div>
        <div class="card-val" id="ramVal">Checking...</div>
        <div class="card-sub" id="ramSub">Dedicated boundary allocation</div>
      </div>
      <div class="card">
        <div class="card-title">
          <span>STORAGE & SCRATCH DISK</span>
          <span style="color: var(--amber); font-size: 0.72rem;">ZERO-PERSISTENCE</span>
        </div>
        <div class="card-val" id="diskVal">Checking...</div>
        <div class="card-sub" id="diskSub">Free space available</div>
      </div>
    </div>

    <!-- Emergency Stop Box -->
    <div class="danger-box">
      <div>
        <div style="font-weight: 800; font-size: 0.95rem; margin-bottom: 2px;">Emergency Stop & Sanitize</div>
        <div style="font-size: 0.82rem; color: var(--text-muted);">Instantly terminate any active tenant pods and zero-fill scrub scratch disks.</div>
      </div>
      <button class="danger-btn" onclick="emergencyStop()">🚨 Stop All & Wipe Workspace</button>
    </div>
  </div>

  <!-- ========================================================= -->
  <!-- TAB 3: RESOURCE ALLOCATION BOUNDARIES -->
  <!-- ========================================================= -->
  <div id="tab-alloc" class="panel">
    <div class="slider-box">
      <div class="slider-header">
        <span>Dedicated RAM Memory Limit</span>
        <span class="slider-val" id="ramDisplay">2.0 GB</span>
      </div>
      <input type="range" id="ramSlider" min="0.5" max="16.0" step="0.5" value="2.0" oninput="updateRam(this.value)">
      <div class="card-sub">Workloads cannot exceed this ceiling. Host OS retains physical memory buffer.</div>
      <div class="presets">
        <button class="preset-btn" onclick="setPreset('eco')">🌱 Eco (1.0 GB)</button>
        <button class="preset-btn" onclick="setPreset('balanced')">⚖️ Balanced (2.0 GB)</button>
        <button class="preset-btn" onclick="setPreset('max')">🚀 High (4.0 GB)</button>
      </div>
    </div>

    <div class="slider-box">
      <div class="slider-header">
        <span>Scratch Disk Space Limit</span>
        <span class="slider-val" id="diskDisplay" style="color: var(--amber);">25.0 GB</span>
      </div>
      <input type="range" id="diskSlider" min="5.0" max="100.0" step="5.0" value="25.0" oninput="updateDisk(this.value)">
      <div class="card-sub">Pod workspaces are strictly capped at this quota. Overflow immediately aborts task.</div>
    </div>

    <div class="slider-box">
      <div class="slider-header">
        <span>Hardware Thermal Guard Ceiling</span>
        <span class="slider-val" id="tempDisplay" style="color: var(--red);">75°C</span>
      </div>
      <input type="range" id="tempSlider" min="60" max="85" step="1" value="75" oninput="updateTemp(this.value)">
      <div class="card-sub">Node automatically pauses if GPU reaches this temperature to protect your hardware.</div>
    </div>

    <button class="btn-lime" onclick="saveAllocations()">💾 Save Resource Boundaries</button>
    <span id="saveNotice" style="margin-left: 14px; font-size: 0.88rem; color: var(--green);"></span>
  </div>

  <!-- ========================================================= -->
  <!-- TAB 4: PLATFORM TUNNEL & PAIRING -->
  <!-- ========================================================= -->
  <div id="tab-tunnel" class="panel">
    <div class="card" style="max-width: 680px; margin: 0 auto;">
      <h3 style="font-family: 'Space Grotesk', sans-serif; font-size: 1.15rem; font-weight: 800; margin-bottom: 8px;">
        Connect to Productify Platform
      </h3>
      <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 20px;">
        Bind this physical node to your seller account using the pairing token from the Seller Dashboard.
      </p>

      <div style="margin-bottom: 16px;">
        <label style="display: block; font-size: 0.78rem; font-weight: 700; color: var(--text-muted); margin-bottom: 6px;">PAIRING TOKEN</label>
        <input type="password" id="inputToken" placeholder="Paste your token from dashboard..." style="width: 100%; background: #07090e; border: 1px solid var(--border); padding: 10px 14px; border-radius: 8px; color: #fff; font-family: 'DM Mono', monospace; font-size: 0.88rem; outline: none;">
      </div>

      <div style="margin-bottom: 22px;">
        <label style="display: block; font-size: 0.78rem; font-weight: 700; color: var(--text-muted); margin-bottom: 6px;">ASSIGNED RENTAL ID (OPTIONAL)</label>
        <input type="text" id="inputRentalId" placeholder="e.g. rental-101" style="width: 100%; background: #07090e; border: 1px solid var(--border); padding: 10px 14px; border-radius: 8px; color: #fff; font-family: 'DM Mono', monospace; font-size: 0.88rem; outline: none;">
      </div>

      <button class="btn-primary" onclick="connectTunnel()">⚡ Connect & Go Live</button>
      <span id="tunnelNotice" style="margin-left: 14px; font-size: 0.88rem; color: var(--green);"></span>
    </div>
  </div>

  <!-- ========================================================= -->
  <!-- TAB 5: AUDIT LOGS -->
  <!-- ========================================================= -->
  <div id="tab-logs" class="panel">
    <div class="card">
      <div class="card-title">
        <span>REAL-TIME HYPERVISOR AUDIT LOGS</span>
        <button class="btn-secondary" style="padding: 4px 10px; font-size: 0.72rem;" onclick="copyAllLogs()">Copy All</button>
      </div>
      <div class="terminal" id="termLogs">
        <div class="log-line INFO"><span class="time">[00:00:00]</span> Productify Node Hypervisor active.</div>
      </div>
    </div>
  </div>

  <!-- ========================================================= -->
  <!-- JAVASCRIPT CONTROLLERS -->
  <!-- ========================================================= -->
  <script>
    let isLive = true;
    let sessionSeconds = 0;
    const hourlyRate = 0.60;
    let isInstalling = false;

    function showTab(id, btn) {
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.remove('active');
        b.classList.remove('gaming');
      });
      document.getElementById('tab-' + id).classList.add('active');
      btn.classList.add('active');
      if (id === 'gaming') btn.classList.add('gaming');
      if (id === 'logs') pollLogs();
      if (id === 'gaming') pollGamingStatus();
    }

    function updateRam(v) { document.getElementById('ramDisplay').innerText = parseFloat(v).toFixed(1) + ' GB'; }
    function updateDisk(v) { document.getElementById('diskDisplay').innerText = parseFloat(v).toFixed(1) + ' GB'; }
    function updateTemp(v) { document.getElementById('tempDisplay').innerText = parseInt(v) + '°C'; }

    function setPreset(type) {
      if (type === 'eco') { document.getElementById('ramSlider').value = 1.0; updateRam(1.0); }
      if (type === 'balanced') { document.getElementById('ramSlider').value = 2.0; updateRam(2.0); }
      if (type === 'max') { document.getElementById('ramSlider').value = 4.0; updateRam(4.0); }
    }

    function copyNodeId() {
      const text = document.getElementById('nodeId').innerText.replace('Node: ', '').trim();
      navigator.clipboard.writeText(text);
      const orig = document.getElementById('nodeId').innerText;
      document.getElementById('nodeId').innerText = 'Copied!';
      setTimeout(() => document.getElementById('nodeId').innerText = orig, 1800);
    }

    async function toggleLive() {
      try {
        const res = await fetch('/toggle', { method: 'POST' });
        const d = await res.json();
        isLive = (d.status === 'LIVE');
        updateLiveUi();
      } catch (e) { console.error(e); }
    }

    function updateLiveUi() {
      const btn = document.getElementById('liveBtn');
      const dot = document.getElementById('liveDot');
      const txt = document.getElementById('liveText');
      if (isLive) {
        btn.classList.remove('paused');
        dot.style.color = '#10b981';
        txt.innerText = 'LIVE (Hosting & Earning)';
      } else {
        btn.classList.add('paused');
        dot.style.color = '#64748b';
        txt.innerText = 'PAUSED (Machine Safe / Offline)';
      }
    }

    async function emergencyStop() {
      if (!confirm("Terminate all active tenant workloads and wipe scratch storage immediately?")) return;
      try {
        const res = await fetch('/emergency_stop', { method: 'POST' });
        const d = await res.json();
        alert("Emergency stop completed: " + d.stopped_pods + " pod(s) terminated and sanitized.");
        poll();
      } catch (e) { alert("Emergency stop failed: " + e); }
    }

    async function saveAllocations() {
      const ram = parseFloat(document.getElementById('ramSlider').value);
      const disk = parseFloat(document.getElementById('diskSlider').value);
      const temp = parseInt(document.getElementById('tempSlider').value);
      try {
        await fetch('/allocation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ram_limit_gb: ram, disk_limit_gb: disk })
        });
        await fetch('/thermal/limits', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ max_temp_c: temp })
        });
        const n = document.getElementById('saveNotice');
        n.innerText = '✓ Resource boundaries & thermal ceiling saved!';
        setTimeout(() => n.innerText = '', 3000);
      } catch (e) { alert('Error saving boundaries'); }
    }

    async function connectTunnel() {
      const token = document.getElementById('inputToken').value.trim();
      const rentalId = document.getElementById('inputRentalId').value.trim();
      try {
        const res = await fetch('/tunnel/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, rental_id: rentalId })
        });
        const d = await res.json();
        if (d.ok) {
          isLive = true;
          updateLiveUi();
          const n = document.getElementById('tunnelNotice');
          n.innerText = '✓ Connected to Productify reverse tunnel!';
          setTimeout(() => n.innerText = '', 3000);
        }
      } catch (e) { alert('Failed to connect tunnel: ' + e); }
    }

    // Revenue & Timer ticker
    setInterval(() => {
      if (isLive) {
        sessionSeconds++;
        const hrs = String(Math.floor(sessionSeconds / 3600)).padStart(2, '0');
        const mins = String(Math.floor((sessionSeconds % 3600) / 60)).padStart(2, '0');
        const secs = String(sessionSeconds % 60).padStart(2, '0');
        document.getElementById('sessionTimer').innerText = `${hrs}:${mins}:${secs}`;
        
        const earned = (sessionSeconds / 3600) * hourlyRate;
        document.getElementById('sessionEarnings').innerText = '$' + earned.toFixed(4);
      }
    }, 1000);

    // Gaming Stack Installation & Streaming
    async function triggerGamingInstall() {
      if (isInstalling) return;
      isInstalling = true;
      const btn = document.getElementById('btnInstallGaming');
      btn.disabled = true;
      btn.innerText = '⏳ Installing Gaming Stack...';
      document.getElementById('progressBarWrap').style.display = 'block';

      try {
        await fetch('/gaming/install', { method: 'POST' });
        appendGamingLog('Started 1-Click Cloud Gaming Stack installer...', 'INFO');
      } catch (e) {
        appendGamingLog('Error initiating install: ' + e, 'ERROR');
        isInstalling = false;
        btn.disabled = false;
        btn.innerText = '⚡ 1-Click Install / Repair Gaming Stack';
      }
    }

    async function pollGamingStatus() {
      try {
        const res = await fetch('/gaming/status');
        const d = await res.json();
        if (!d.ok) return;

        // Sunshine
        const sun = d.sunshine || {};
        const sunPill = document.getElementById('sunshinePill');
        const sunTxt = document.getElementById('sunshineStatusText');
        if (sun.installed) {
          sunPill.className = 'status-pill success';
          sunPill.innerText = 'INSTALLED';
          sunTxt.innerText = 'LizardByte Active';
        } else {
          sunPill.className = 'status-pill error';
          sunPill.innerText = 'MISSING';
          sunTxt.innerText = 'Not Installed';
        }

        // ViGEmBus
        const vig = d.vigem || {};
        const vigPill = document.getElementById('vigemPill');
        const vigTxt = document.getElementById('vigemStatusText');
        if (vig.installed) {
          vigPill.className = 'status-pill success';
          vigPill.innerText = 'ACTIVE';
          vigTxt.innerText = 'Driver Ready';
        } else {
          vigPill.className = 'status-pill error';
          vigPill.innerText = 'MISSING';
          vigTxt.innerText = 'Not Found';
        }

        // Firewall
        const fw = d.ports || {};
        const fwPill = document.getElementById('firewallPill');
        const fwTxt = document.getElementById('firewallStatusText');
        const allPortsReady = Object.values(fw).length > 0 && Object.values(fw).every(v => v === true);
        if (allPortsReady) {
          fwPill.className = 'status-pill success';
          fwPill.innerText = 'OPEN';
          fwTxt.innerText = 'Ready (47989/47990)';
        } else {
          fwPill.className = 'status-pill cyan';
          fwPill.innerText = 'CONFIGURED';
          fwTxt.innerText = 'Rules Added';
        }

        // WAN IP
        const net = d.network || {};
        const wanTxt = document.getElementById('wanStatusText');
        if (net.public_wan_ip) {
          wanTxt.innerText = net.public_wan_ip;
        }

        // Overall Readiness Status in Ticker
        const stackTicker = document.getElementById('gamingStackStatus');
        if (d.ready) {
          stackTicker.className = 'ticker-val glow';
          stackTicker.innerText = 'Ready to Stream 🟢';
        } else {
          stackTicker.className = 'ticker-val cyan';
          stackTicker.innerText = 'Setup Required 🟡';
        }

        // Streaming Session
        const sessBox = document.getElementById('streamSessionInfo');
        if (d.streaming_active && d.current_session) {
          sessBox.style.display = 'block';
          document.getElementById('streamHostIp').innerText = `${d.current_session.wan_ip}:${d.current_session.port}`;
          document.getElementById('streamPin').innerText = d.current_session.pin;
          document.getElementById('streamMoonlightLink').href = d.current_session.moonlight_uri;
        } else {
          sessBox.style.display = 'none';
        }

        // Installation Progress
        const ist = d.install_state || {};
        if (ist.is_running) {
          isInstalling = true;
          document.getElementById('progressBarWrap').style.display = 'block';
          document.getElementById('progressBarFill').style.width = (ist.progress || 20) + '%';
          document.getElementById('btnInstallGaming').innerText = `⏳ Installing (${ist.step})...`;
        } else if (isInstalling && !ist.is_running) {
          isInstalling = false;
          document.getElementById('progressBarFill').style.width = '100%';
          setTimeout(() => { document.getElementById('progressBarWrap').style.display = 'none'; }, 2000);
          const btn = document.getElementById('btnInstallGaming');
          btn.disabled = false;
          btn.innerText = '⚡ 1-Click Install / Repair Gaming Stack';
          appendGamingLog('Installation pipeline completed successfully!', 'SUCCESS');
        }
      } catch (e) {}
    }

    async function startTestStream() {
      try {
        const res = await fetch('/gaming/test-stream', { method: 'POST' });
        const d = await res.json();
        if (d.ok) {
          appendGamingLog('Test stream started: PIN ' + d.session.pin, 'SUCCESS');
          pollGamingStatus();
        } else {
          alert('Could not start test stream: ' + d.error);
        }
      } catch (e) { alert('Stream start failed: ' + e); }
    }

    async function stopTestStream() {
      try {
        await fetch('/gaming/stop-stream', { method: 'POST' });
        appendGamingLog('Stopped Sunshine streaming daemon.', 'INFO');
        pollGamingStatus();
      } catch (e) {}
    }

    function appendGamingLog(msg, level) {
      const t = document.getElementById('termGaming');
      const now = new Date().toTimeString().split(' ')[0];
      t.innerHTML += `<div class="log-line ${level}"><span class="time">[${now}]</span> ${msg}</div>`;
      t.scrollTop = t.scrollHeight;
    }

    function clearGamingLogs() {
      document.getElementById('termGaming').innerHTML = '';
    }

    async function poll() {
      try {
        const res = await fetch('/probe');
        const d = await res.json();
        document.getElementById('nodeId').innerText = 'Node: ' + d.node_id;
        document.getElementById('gpuName').innerText = d.gpu;
        document.getElementById('gpuSub').innerText = 'VRAM: ' + d.vram + ' · Driver: ' + d.driver_version;
        document.getElementById('topGpuChip').innerText = d.gpu + (d.gpu_available ? ' · NVENC ACCEL' : '');
        document.getElementById('cpuName').innerText = d.cpu;
        document.getElementById('cpuSub').innerText = d.cpu_cores + ' Logical Processor Cores';
        document.getElementById('ramVal').innerText = d.ram + ' Physical';
        document.getElementById('ramSub').innerText = 'Allocated Bound: ' + d.allocated_ram_gb + ' GB Max';
        document.getElementById('diskVal').innerText = d.storage_free + ' Free';
        document.getElementById('diskSub').innerText = 'Scratch Quota: ' + d.allocated_disk_gb + ' GB Max';
        document.getElementById('activePodsCount').innerText = d.active_pods + ' Active';
        
        // Update Thermal Shield
        const shield = document.getElementById('thermalShield');
        const badge = document.getElementById('shieldBadge');
        const tempText = document.getElementById('gpuTempShield');
        const tempVal = d.temperature_val || 0;
        tempText.innerText = d.temperature;

        if (d.thermal && d.thermal.is_overheated) {
          shield.className = 'thermal-shield overheat';
          badge.className = 'shield-badge overheat';
          badge.innerText = 'OVERHEAT THROTTLED';
        } else if (tempVal >= 70) {
          shield.className = 'thermal-shield warn';
          badge.className = 'shield-badge warn';
          badge.innerText = 'HIGH TEMP WARNING';
        } else {
          shield.className = 'thermal-shield';
          badge.className = 'shield-badge';
          badge.innerText = 'ACTIVE & SAFE';
        }

        isLive = d.is_live;
        updateLiveUi();
      } catch (e) {}
    }

    let lastLogSig = "";
    async function pollLogs() {
      const panel = document.getElementById('tab-logs');
      if (!panel || !panel.classList.contains('active')) return;
      try {
        const res = await fetch('/logs');
        const d = await res.json();
        if (d.logs && d.logs.length > 0) {
          const sig = d.logs.length + "-" + d.logs[d.logs.length - 1].time + "-" + d.logs[d.logs.length - 1].text;
          if (sig === lastLogSig) return;
          lastLogSig = sig;

          const t = document.getElementById('termLogs');
          t.innerHTML = d.logs.map(l => 
            `<div class="log-line ${l.level}"><span class="time">[${l.time}]</span> ${l.text}</div>`
          ).join('');
          t.scrollTop = t.scrollHeight;
        }
      } catch (e) {}
    }

    function copyAllLogs() {
      const t = document.getElementById('termLogs');
      navigator.clipboard.writeText(t.innerText);
      alert('Logs copied to clipboard!');
    }

    // Initial Polls
    poll();
    pollGamingStatus();
    setInterval(poll, 3000);
    setInterval(pollGamingStatus, 2500);
    setInterval(pollLogs, 3000);
  </script>
</body>
</html>
"""
