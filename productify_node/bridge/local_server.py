"""Local loopback HTTP bridge (127.0.0.1:48123) for browser integration and Webview GUI."""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
from productify_node.config import config
from productify_node.state import node_state
from productify_node.boundary import enforcer
from productify_node.telemetry import get_full_telemetry
from productify_node.thermal_guard import thermal_guard
from productify_node.container import container_mgr

logger = logging.getLogger("productify_node.bridge")


class BridgeHandler(BaseHTTPRequestHandler):
    """Handles local loopback requests from the seller dashboard and embedded webview."""

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
            thermal = thermal_guard.get_status()
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
  <title>Productify Node — Provider Hypervisor</title>
  <style>
    :root {
      --bg: #07090d;
      --card: #11141b;
      --card-hover: #161b24;
      --border: #222936;
      --border-glow: #2d3748;
      --text: #f8fafc;
      --muted: #94a3b8;
      --lime: #c8f04c;
      --green: #10b981;
      --amber: #f59e0b;
      --red: #ef4444;
      --cyan: #38bdf8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 24px; max-width: 1060px; margin: 0 auto; line-height: 1.5; -webkit-font-smoothing: antialiased; }
    
    /* Header & Branding */
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; flex-wrap: wrap; gap: 14px; }
    .brand-wrap { display: flex; align-items: center; gap: 14px; }
    .brand { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em; display: flex; align-items: center; gap: 6px; }
    .brand span { color: var(--lime); }
    .badge-version { font-size: 0.68rem; font-weight: 800; background: rgba(200, 240, 76, 0.12); color: var(--lime); border: 1px solid rgba(200, 240, 76, 0.3); padding: 2px 7px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
    .node-id { font-size: 0.78rem; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--card); padding: 4px 10px; border-radius: 6px; border: 1px solid var(--border); }
    
    /* Live/Pause Toggle button */
    .controls-wrap { display: flex; align-items: center; gap: 12px; }
    .live-toggle-btn { background: var(--green); color: #042f2e; border: none; padding: 10px 22px; border-radius: 9px; font-weight: 800; font-size: 0.9rem; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 0 20px rgba(16, 185, 129, 0.25); }
    .live-toggle-btn:hover { transform: translateY(-1px); box-shadow: 0 0 25px rgba(16, 185, 129, 0.4); }
    .live-toggle-btn.paused { background: #1e293b; color: #cbd5e1; box-shadow: none; border: 1px solid var(--border); }
    .live-toggle-btn.paused:hover { background: #273549; }
    
    /* Revenue & Session Meter Ticker */
    .ticker-bar { display: flex; align-items: center; justify-content: space-between; background: linear-gradient(90deg, rgba(200, 240, 76, 0.06), rgba(56, 189, 248, 0.04)); border: 1px solid rgba(200, 240, 76, 0.25); border-radius: 12px; padding: 12px 20px; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
    .ticker-item { display: flex; flex-direction: column; }
    .ticker-label { font-size: 0.72rem; text-transform: uppercase; font-weight: 700; color: var(--muted); letter-spacing: 0.05em; }
    .ticker-val { font-size: 1.15rem; font-weight: 800; color: var(--text); font-family: ui-monospace, Menlo, monospace; }
    .ticker-val.glow { color: var(--lime); text-shadow: 0 0 12px rgba(200, 240, 76, 0.3); }

    /* Thermal Protection Shield Banner */
    .thermal-shield { display: flex; align-items: center; justify-content: space-between; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 10px 18px; margin-bottom: 20px; font-size: 0.85rem; }
    .thermal-shield.warn { background: rgba(245, 158, 11, 0.08); border-color: rgba(245, 158, 11, 0.35); }
    .thermal-shield.overheat { background: rgba(239, 68, 68, 0.12); border-color: rgba(239, 68, 68, 0.4); animation: pulse 1.5s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
    .shield-badge { font-weight: 800; font-size: 0.75rem; padding: 3px 9px; border-radius: 6px; background: rgba(16, 185, 129, 0.2); color: var(--green); text-transform: uppercase; }
    .shield-badge.warn { background: rgba(245, 158, 11, 0.2); color: var(--amber); }
    .shield-badge.overheat { background: rgba(239, 68, 68, 0.25); color: var(--red); }

    /* Tabs */
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
    .tab-btn { background: transparent; border: none; color: var(--muted); padding: 8px 18px; border-radius: 8px; font-size: 0.88rem; font-weight: 700; cursor: pointer; transition: all 0.15s ease; }
    .tab-btn:hover { color: var(--text); background: rgba(255, 255, 255, 0.03); }
    .tab-btn.active { background: var(--card); color: var(--text); border: 1px solid var(--border); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3); }

    .panel { display: none; }
    .panel.active { display: block; }

    /* Grid & Cards */
    .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; transition: border-color 0.2s ease; }
    .card:hover { border-color: var(--border-glow); }
    .card-title { font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
    .card-val { font-size: 1.25rem; font-weight: 800; color: var(--text); margin-bottom: 4px; word-break: break-word; }
    .card-sub { font-size: 0.82rem; color: var(--muted); }
    
    /* Allocation Sliders */
    .slider-box { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 22px; margin-bottom: 16px; }
    .slider-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 700; font-size: 0.94rem; }
    .slider-val { font-size: 1.15rem; font-weight: 800; color: var(--lime); font-family: ui-monospace, Menlo, monospace; }
    input[type=range] { width: 100%; height: 6px; background: #222936; border-radius: 4px; outline: none; margin: 14px 0; accent-color: var(--lime); cursor: pointer; }
    .presets { display: flex; gap: 8px; margin-top: 10px; }
    .preset-btn { background: var(--card-hover); color: var(--text); border: 1px solid var(--border); padding: 6px 14px; border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; }
    .preset-btn:hover { border-color: var(--lime); color: var(--lime); }
    
    .save-btn { background: var(--lime); color: #090b0e; border: none; padding: 12px 26px; border-radius: 8px; font-weight: 800; font-size: 0.92rem; cursor: pointer; transition: all 0.2s ease; }
    .save-btn:hover { background: #b6dc3e; transform: translateY(-1px); }
    
    /* Emergency Stop Box */
    .danger-box { background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 12px; padding: 22px; margin-top: 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px; }
    .danger-btn { background: #ef4444; color: #fff; border: none; padding: 11px 22px; border-radius: 8px; font-weight: 800; font-size: 0.88rem; cursor: pointer; transition: all 0.2s ease; }
    .danger-btn:hover { background: #dc2626; box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }

    /* Terminal & Logs */
    .terminal { background: #050609; border: 1px solid var(--border); border-radius: 10px; padding: 16px; font-family: ui-monospace, Menlo, Monaco, monospace; font-size: 0.8rem; height: 340px; overflow-y: auto; color: #cbd5e1; line-height: 1.6; }
    .terminal .log-line { margin-bottom: 2px; }
    .terminal .time { color: var(--muted); margin-right: 8px; }
    .terminal .INFO { color: #cbd5e1; }
    .terminal .WARNING { color: #f59e0b; }
    .terminal .ERROR { color: #ef4444; font-weight: 700; }
  </style>
</head>
<body>
  <header>
    <div class="brand-wrap">
      <div class="brand">⚡ PRODUCTIFY <span>NODE</span></div>
      <div class="badge-version">v1.2.0 Guarded</div>
      <div class="node-id" id="nodeId">Node: Probing...</div>
    </div>
    <div class="controls-wrap">
      <button id="liveBtn" class="live-toggle-btn" onclick="toggleLive()">
        <span id="liveDot">🟢</span> <span id="liveText">LIVE (Earning)</span>
      </button>
    </div>
  </header>

  <!-- Live Revenue & Metering Ticker -->
  <div class="ticker-bar">
    <div class="ticker-item">
      <div class="ticker-label">Active Session Time</div>
      <div class="ticker-val" id="sessionTimer">00:00:00</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Hourly Earning Rate</div>
      <div class="ticker-val glow" id="earningRate">$0.50 / hr</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Estimated Session Earnings</div>
      <div class="ticker-val glow" id="sessionEarnings">$0.0000</div>
    </div>
    <div class="ticker-item">
      <div class="ticker-label">Active Pods</div>
      <div class="ticker-val" id="activePodsCount">0 Active</div>
    </div>
  </div>

  <!-- Hardware Thermal Guard Shield Banner -->
  <div class="thermal-shield" id="thermalShield">
    <div style="display: flex; align-items: center; gap: 10px;">
      <span style="font-size: 1.2rem;">🛡️</span>
      <div>
        <b>Hardware Thermal Guard:</b> Max safe GPU threshold locked at <b>75°C</b>.
        Current: <b id="gpuTempShield">--°C</b>
      </div>
    </div>
    <div class="shield-badge" id="shieldBadge">ACTIVE & SAFE</div>
  </div>

  <!-- Tabs Navigation -->
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('dash', this)">📊 Hardware Telemetry</button>
    <button class="tab-btn" onclick="showTab('alloc', this)">🛡️ Memory & Space Limits</button>
    <button class="tab-btn" onclick="showTab('logs', this)">📋 Logs & Pods</button>
  </div>

  <!-- TAB 1: Hardware Dashboard -->
  <div id="tab-dash" class="panel active">
    <div class="grid-2">
      <div class="card">
        <div class="card-title">
          <span>GPU ACCELERATION</span>
          <span style="color: var(--lime); font-size: 0.72rem;">PASSTHROUGH</span>
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

    <!-- Danger / Emergency Stop Area -->
    <div class="danger-box">
      <div>
        <div style="font-weight: 800; font-size: 0.95rem; margin-bottom: 2px;">Emergency Stop & Sanitize</div>
        <div style="font-size: 0.82rem; color: var(--muted);">Instantly terminate any active tenant pods and zero-fill scrub scratch disks.</div>
      </div>
      <button class="danger-btn" onclick="emergencyStop()">🚨 Stop All & Wipe Workspace</button>
    </div>
  </div>

  <!-- TAB 2: Resource Allocation Boundaries -->
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

    <button class="save-btn" onclick="saveAllocations()">💾 Save Resource Boundaries</button>
    <span id="saveNotice" style="margin-left: 12px; font-size: 0.85rem; color: var(--green);"></span>
  </div>

  <!-- TAB 3: Audit Logs -->
  <div id="tab-logs" class="panel">
    <div class="card-title" style="margin-bottom: 8px;">REAL-TIME HYPERVISOR AUDIT LOGS</div>
    <div class="terminal" id="termLogs">
      <div class="log-line"><span class="time">[00:00:00]</span> Productify Node Hypervisor active.</div>
    </div>
  </div>

  <script>
    let isLive = true;
    let sessionSeconds = 0;
    const hourlyRate = 0.50; // $0.50 per hour baseline

    function showTab(id, btn) {
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById('tab-' + id).classList.add('active');
      btn.classList.add('active');
      if (id === 'logs') pollLogs();
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

    async function emergencyStop() {
      if (!confirm("Stop all running pods and wipe scratch storage immediately?")) return;
      try {
        const res = await fetch('/emergency_stop', { method: 'POST' });
        const d = await res.json();
        alert("Emergency stop completed: " + d.stopped_pods + " pod(s) terminated and wiped.");
        poll();
      } catch (e) { alert("Emergency stop failed: " + e); }
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

    async function poll() {
      try {
        const res = await fetch('/probe');
        const d = await res.json();
        document.getElementById('nodeId').innerText = 'Node: ' + d.node_id;
        document.getElementById('gpuName').innerText = d.gpu;
        document.getElementById('gpuSub').innerText = 'VRAM: ' + d.vram + ' · Driver: ' + d.driver_version;
        document.getElementById('cpuName').innerText = d.cpu;
        document.getElementById('cpuSub').innerText = d.cpu_cores + ' logical processor cores';
        document.getElementById('ramVal').innerText = d.ram + ' Total';
        document.getElementById('ramSub').innerText = 'Allocated Bound: ' + d.allocated_ram_gb + ' GB Max';
        document.getElementById('diskVal').innerText = d.storage_free + ' Free';
        document.getElementById('diskSub').innerText = 'Allocated Scratch: ' + d.allocated_disk_gb + ' GB Max';
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

    async function pollLogs() {
      try {
        const res = await fetch('/logs');
        const d = await res.json();
        if (d.logs) {
          const t = document.getElementById('termLogs');
          t.innerHTML = d.logs.map(l => 
            `<div class="log-line ${l.level}"><span class="time">[${l.time}]</span> ${l.text}</div>`
          ).join('');
          t.scrollTop = t.scrollHeight;
        }
      } catch (e) {}
    }

    poll();
    setInterval(poll, 3000);
    setInterval(pollLogs, 4000);
  </script>
</body>
</html>
"""
