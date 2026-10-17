// Productify Node UI. All data comes from the local agent through the `agent` command.
"use strict";

const { invoke } = window.__TAURI__.core;
const $ = (id) => document.getElementById(id);
const call = (op, args) => invoke("agent", { op, args: args || null });

let current = null;
let repairing = false;

function showError(msg) {
  $("error").textContent = msg;
  $("error").hidden = !msg;
}

function text(el, value) {
  $(el).textContent = value;
}

function render(data) {
  current = data;
  const s = data.status;
  const cfg = data.settings;
  const paired = s.paired && !repairing;
  $("pair-view").hidden = paired;
  $("main-view").hidden = !paired;

  const state = $("state");
  state.className = "state " + (s.paused_reason === "thermal" ? "hot" : s.live ? "live" : "off");
  state.textContent = !s.paired ? "Not paired" : s.paused_reason === "thermal" ? "Cooling down" : s.live ? "Renting" : "Paused";
  if (!paired) return;

  text("listing", cfg.rental_id);
  const headline = s.paused_reason === "thermal" ? "Paused — GPU too hot"
    : s.live ? (s.jobs ? `Renting · ${s.jobs} job${s.jobs === 1 ? "" : "s"} running` : "Renting · waiting for a renter")
    : "Paused";
  text("headline", headline);
  text("subline", !s.docker ? "Docker Desktop isn't running, so no jobs can start. Open Docker Desktop to rent this computer."
    : s.live ? "Renters on productifynow.com can start jobs on this computer."
    : "Renters can't start new jobs. Jobs already running keep going.");

  const live = $("live-btn");
  live.textContent = s.live ? "Pause renting" : "Start renting";
  live.className = s.live ? "secondary" : "primary";
  live.disabled = s.paused_reason === "thermal" || (!s.live && !s.docker);

  text("s-docker", s.docker ? "Running" : "Not running");
  text("s-gpu", s.gpu ? `${s.gpu}${cfg.share_gpu ? (s.gpu_in_docker ? " · shared" : " · not usable in Docker") : " · not shared"}` : "No NVIDIA GPU found");
  text("s-temp", s.gpu_temp_c == null ? "—" : `${s.gpu_temp_c} °C (limit ${cfg.max_gpu_temp_c})`);
  text("s-jobs", String(s.jobs));

  // Only fill the limits form when it isn't being edited.
  if (!$("limits-form").contains(document.activeElement)) {
    $("l-mem").value = cfg.memory_mb;
    $("l-cpu").value = cfg.cpus;
    $("l-disk").value = cfg.disk_gb;
    $("l-temp").value = cfg.max_gpu_temp_c;
    $("l-gpu").checked = cfg.share_gpu;
  }
}

async function refresh() {
  try {
    render(await call("status"));
    showError("");
  } catch (e) {
    $("state").className = "state off";
    $("state").textContent = "Service not running";
    showError(String(e));
  }
}

async function refreshLogs() {
  try {
    const lines = await call("logs");
    const ol = $("logs");
    ol.replaceChildren(...lines.slice(-40).reverse().map((l) => {
      const li = document.createElement("li");
      li.className = l.level.toLowerCase();
      const time = document.createElement("time");
      time.textContent = new Date(l.time).toLocaleTimeString();
      const msg = document.createElement("span");
      const extra = l.attrs && (l.attrs.job || l.attrs.err || l.attrs.temp_c);
      msg.textContent = l.message + (extra ? ` · ${extra}` : "");
      li.append(time, msg);
      return li;
    }));
  } catch {
    /* shown by refresh() */
  }
}

async function act(fn, okMsg) {
  try {
    showError("");
    await fn();
    if (okMsg) flash(okMsg);
    await refresh();
    refreshLogs();
  } catch (e) {
    showError(String(e));
  }
}

function flash(msg) {
  const el = $("state");
  const prev = el.textContent;
  el.textContent = msg;
  setTimeout(() => { if (el.textContent === msg) el.textContent = prev; }, 1500);
}

$("pair-form").addEventListener("submit", (e) => {
  e.preventDefault();
  act(async () => {
    await call("pair", { code: $("code").value.trim() });
    $("code").value = "";
    repairing = false;
  }, "Paired");
});

$("live-btn").addEventListener("click", () => {
  if (!current) return;
  act(() => call("live", { live: !current.status.live }));
});

$("stop-btn").addEventListener("click", () => {
  if (!confirm("Stop every renter job now and pause renting?")) return;
  act(() => call("emergency_stop"), "Stopped");
});

$("limits-form").addEventListener("submit", (e) => {
  e.preventDefault();
  act(() => call("limits", {
    memory_mb: Number($("l-mem").value),
    cpus: Number($("l-cpu").value),
    disk_gb: Number($("l-disk").value),
    max_gpu_temp_c: Number($("l-temp").value),
    share_gpu: $("l-gpu").checked,
  }), "Saved");
});

$("repair-btn").addEventListener("click", () => {
  repairing = true;
  if (current) render(current);
});

refresh();
refreshLogs();
setInterval(refresh, 3000);
setInterval(refreshLogs, 5000);
