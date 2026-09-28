"""Local loopback HTTP bridge (127.0.0.1:48123) for browser integration."""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
from productify_node.config import config
from productify_node.state import node_state
from productify_node.boundary import enforcer
from productify_node.telemetry import get_full_telemetry

logger = logging.getLogger("productify_node.bridge")


class BridgeHandler(BaseHTTPRequestHandler):
    """Handles local loopback requests from the seller dashboard in the browser."""

    def _set_cors(self, status=200):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors(200)

    def do_GET(self):
        if self.path.startswith("/probe") or self.path == "/":
            telemetry = get_full_telemetry()
            data = {
                "ok": True,
                "node_id": config.node_id,
                "node_name": config.get("node_name"),
                "status": node_state.status,
                "is_live": node_state.is_live,
                "gpu": telemetry["gpu"]["name"] if telemetry["gpu"]["available"] else "CPU Compute Node",
                "vram": f"{round(telemetry['gpu']['vram_total_mb'] / 1024, 1)} GB" if telemetry["gpu"]["available"] else "N/A",
                "cpu": telemetry["cpu"]["name"],
                "cpu_cores": telemetry["cpu"]["cores"],
                "ram": f"{telemetry['ram']['total_gb']} GB",
                "storage_free": f"{telemetry['disk']['free_gb']} GB",
                "temperature": f"{telemetry['gpu']['temperature_c']}°C" if telemetry["gpu"]["available"] else "N/A",
                "driver_version": telemetry["gpu"]["driver_version"],
                "allocated_ram_gb": config.ram_limit_gb,
                "allocated_disk_gb": config.disk_limit_gb,
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
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
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
            rental_id = payload.get("rental_id")
            token = payload.get("token")
            if rental_id:
                config.set("rental_id", rental_id)
            if token:
                config.set("pairing_token", token)
            node_state.set_live()
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "status": "LIVE"}).encode("utf-8"))

        elif self.path == "/toggle":
            new_status = node_state.toggle_live_pause()
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "status": new_status}).encode("utf-8"))

        elif self.path == "/allocation":
            ram = payload.get("ram_limit_gb")
            disk = payload.get("disk_limit_gb")
            res = enforcer.set_allocations(ram, disk)
            self._set_cors(200)
            self.wfile.write(json.dumps({"ok": True, "allocations": res}).encode("utf-8"))
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

    def start(self):
        try:
            self.server = HTTPServer(("127.0.0.1", self.port), BridgeHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            node_state.log(f"Local bridge server listening on http://127.0.0.1:{self.port}", "INFO")
        except Exception as e:
            logger.warning(f"Could not bind bridge server on port {self.port}: {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()


local_bridge = LocalBridgeServer()
