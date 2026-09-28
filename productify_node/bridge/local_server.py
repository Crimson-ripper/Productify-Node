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

HTML_UI_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Productify Node — Provider Dashboard</title>
  <style>
    :root {
      --bg: #090b0e;
      --card: #14171d;
      --card-hover: #1c212a;
      --border: #262c36;
      --text: #f8fafc;
      --muted: #94a3b8;
      --lime: #c8f04c;
      --green: #10b981;
      --amber: #f59e0b;
      --red: #ef4444;
      --cyan: #38bdf8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 24px; max-width: 1000px; margin: 0 auto; line-height: 1.5; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
    .brand { display: flex; align-items: center; gap: 8px; font-size: 1.4rem; font-weight: 800; letter-spacing: -0.02em; }
    .brand span { color: var(--lime); }
    .node-id { font-size: 0.8rem; color: var(--muted); font-family: monospace; background: var(--card); padding: 4px 10px; border-radius: 6px; border: 1px solid var(--border); }
    .live-toggle-btn { background: var(--green); color: #000; border: none; padding: 10px 22px; border-radius: 8px; font-weight: 800; font-size: 0.92rem; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s ease; }
    .live-toggle-btn.paused { background: #334155; color: #cbd5e1; }
    
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
    .tab-btn { background: transparent; border: none; color: var(--muted); padding: 8px 16px; border-radius: 6px; font-size: 0.88rem; font-weight: 700; cursor: pointer; transition: all 0.15s ease; }
    .tab-btn.active { background: var(--card); color: var(--text); border: 1px solid var(--border); }
    
    .panel { display: none; }
    .panel.active { display: block; }

    .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; transition: border-color 0.2s ease; }
    .card:hover { border-color: #3b4252; }
    .card-title { font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
    .card-val { font-size: 1.25rem; font-weight: 800; color: var(--text); margin-bottom: 4px; }
    .card-sub { font-size: 0.82rem; color: var(--muted); }
    
    .slider-box { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-bottom: 16px; }
    .slider-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 700; font-size: 0.95rem; }
    .slider-val { font-size: 1.1rem; font-weight: 800; color: var(--lime); font-family: monospace; }
    input[type=range] { width: 100%; height: 6px; background: #262c36; border-radius: 4px; outline: none; margin: 12px 0; accent-color: var(--lime); cursor: pointer; }
    .presets { display: flex; gap: 8px; margin-top: 10px; }
    .preset-btn { background: var(--card-hover); color: var(--text); border: 1px solid var(--border); padding: 5px 12px; border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; }
    .preset-btn:hover { border-color: var(--lime); }
    
    .save-btn { background: var(--lime); color: #101112; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 800; font-size: 0.92rem; cursor: pointer; margin-top: 10px; }
    .save-btn:hover { background: #b6dc3e; }
    
    .terminal { background: #050608; border: 1px solid var(--border); border-radius: 10px; padding: 16px; font-family: monospace; font-size: 0.8rem; height: 320px; overflow-y: auto; color: #cbd5e1; }
    .terminal .log-line { margin-bottom: 4px; }
    .terminal .time { color: var(--muted); margin-right: 6px; }
  </style>
</head>
<body>
  <header>
    <div>
      <div class="brand">⚡ PRODUCTIFY <span>NODE</span></div>
      <div class="node-id" id="nodeId">Node ID: Loading...</div>
    </div>
    <button id="liveBtn" class="live-toggle-btn" onclick="toggleLive()">
      <span id="liveDot">🟢</span> <span id="liveText">LIVE (Earning)</span>
    </button>
  </header>

  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('dash', this)">📊 Hardware Telemetry</button>
    <button class="tab-btn" onclick="showTab('alloc', this)">🛡️ Memory & Space Allocation</button>
    <button class="tab-btn" onclick="showTab('logs', this)">📋 Logs & Pods</button>
  </div>

  <!-- TAB 1: Dashboard -->
  <div id="tab-dash" class="panel active">
    <div class="grid-2">
      <div class="card">
        <div class="card-title">GPU ACCELERATION</div>
        <div class="card-val" id="gpuName">Checking...</div>
        <div class="card-sub" id="gpuSub">VRAM & Driver query in progress</div>
      </div>
      <div class="card">
        <div class="card-title">CPU PROCESSOR</div>
        <div class="card-val" id="cpuName">Checking...</div>
        <div class="card-sub" id="cpuSub">Cores & Threads</div>
      </div>
      <div class="card">
        <div class="card-title">SYSTEM RAM MEMORY</div>
        <div class="card-val" id="ramVal">Checking...</div>
        <div class="card-sub" id="ramSub">Dedicated Allocation</div>
      </div>
      <div class="card">
        <div class="card-title">STORAGE & SCRATCH DISK</div>
        <div class="card-val" id="diskVal">Checking...</div>
        <div class="card-sub" id="diskSub">Free space available</div>
      </div>
    </div>
  </div>

  <!-- TAB 2: Allocation -->
  <div id="tab-alloc" class="panel">
    <div class="slider-box">
      <div class="slider-header">
        <span>Dedicated RAM Memory Limit</span>
        <span class="slider-val" id="ramDisplay">2.0 GB</span>
      </div>
      <input type="range" id="ramSlider" min="0.5" max="16.0" step="0.5" value="2.0" oninput="updateRam(this.value)">
      <div class="card-sub">Workloads cannot exceed this ceiling. Host OS retains safety buffer.</div>
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

    <button class="save-btn" onclick="saveAllocations()">💾 Save Resource Boundaries</button>
    <span id="saveNotice" style="margin-left: 12px; font-size: 0.85rem; color: var(--green);"></span>
  </div>

  <!-- TAB 3: Logs -->
  <div id="tab-logs" class="panel">
    <div class="card-title" style="margin-bottom: 8px;">AUDIT TRAIL & LOGS</div>
    <div class="terminal" id="termLogs">
      <div class="log-line"><span class="time">[00:00:00]</span> Productify Node Hypervisor active.</div>
    </div>
  </div>

  <script>
    let isLive = true;
    function showTab(id, btn) {
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById('tab-' + id).classList.add('active');
      btn.classList.add('active');
    }

    function updateRam(v) { document.getElementById('ramDisplay').innerText = parseFloat(v).toFixed(1) + ' GB'; }
    function updateDisk(v) { document.getElementById('diskDisplay').innerText = parseFloat(v).toFixed(1) + ' GB'; }

    function setPreset(type) {
      if (type === 'eco') { document.getElementById('ramSlider').value = 1.0; updateRam(1.0); }
      if (type === 'balanced') { document.getElementById('ramSlider').value = 2.0; updateRam(2.0); }
      if (type === 'max') { document.getElementById('ramSlider').value = 4.0; updateRam(4.0); }
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
        dot.innerText = '🟢';
        txt.innerText = 'LIVE (Available on Marketplace)';
      } else {
        btn.classList.add('paused');
        dot.innerText = '⏸️';
        txt.innerText = 'PAUSED (Machine Safe / Offline)';
      }
    }

    async function saveAllocations() {
      const ram = parseFloat(document.getElementById('ramSlider').value);
      const disk = parseFloat(document.getElementById('diskSlider').value);
      try {
        await fetch('/allocation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ram_limit_gb: ram, disk_limit_gb: disk })
        });
        const n = document.getElementById('saveNotice');
        n.innerText = '✓ Boundaries saved and locked to container engine!';
        setTimeout(() => n.innerText = '', 3000);
      } catch (e) { alert('Error saving boundaries'); }
    }

    async function poll() {
      try {
        const res = await fetch('/probe');
        const d = await res.json();
        document.getElementById('nodeId').innerText = 'Node: ' + d.node_id;
        document.getElementById('gpuName').innerText = d.gpu;
        document.getElementById('gpuSub').innerText = 'VRAM: ' + d.vram + ' · Temp: ' + d.temperature;
        document.getElementById('cpuName').innerText = d.cpu;
        document.getElementById('cpuSub').innerText = d.cpu_cores + ' logical processor threads';
        document.getElementById('ramVal').innerText = d.ram + ' Total';
        document.getElementById('ramSub').innerText = 'Allocated Bound: ' + d.allocated_ram_gb + ' GB Max';
        document.getElementById('diskVal').innerText = d.storage_free + ' Free';
        document.getElementById('diskSub').innerText = 'Allocated Scratch: ' + d.allocated_disk_gb + ' GB Max';
        isLive = d.is_live;
        updateLiveUi();
      } catch (e) {}
    }

    poll();
    setInterval(poll, 3000);
  </script>
</body>
</html>
"""

