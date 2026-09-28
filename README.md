# ⚡ Productify Node

> **Official Desktop Client & Host Hypervisor for Physical GPU & Compute Providers on [Productify](https://productifynow.com).**

Productify Node connects your physical computer (and NVIDIA GPU) directly to the Productify global compute marketplace across any home router, NAT, or firewall without port forwarding.

Renters deploy containerized deep learning workloads and Python tasks on your machine, while **you maintain 100% control over hardware boundaries, live availability, thermal safeguards, and data security.**

---

## 🌟 Key Industry-Standard Features

### 1. 🛡️ Active Hardware & Thermal Protection Guard
Host hardware safety is the number one priority:
- **Continuous Thermal Monitoring**: Probes GPU core temperatures directly from physical hardware sensors every 5 seconds.
- **Auto-Throttle & Auto-Pause**: If your GPU reaches 75°C (configurable via `--max-temp`), the hypervisor immediately auto-pauses the node and suspends workloads to prevent thermal wear or damage.
- **Smart Cooldown & Hysteresis**: Protects against rapid cycling, waiting until temperatures normalize below 62°C before signaling ready state.

### 2. 📌 Industry-Standard System Tray Daemon & Minimize-to-Tray
Operate seamlessly in the background without cluttering your desktop:
- **Live Taskbar Indicator**: Dynamic status icon reflects your node's real-time state:
  - 🟢 **Emerald Green**: LIVE and available for marketplace workloads.
  - ⏸️ **Amber**: PAUSED, offline, and machine completely safe.
  - 🔴 **Crimson Red**: Thermal Guard alert / critical overheat protection active.
- **Quick Right-Click Menu**: Toggle Live/Pause, Open Dashboard, trigger Emergency Stop, or Exit directly from the taskbar.
- **Minimize to Tray**: Clicking the `X` button keeps your node running silently in the system tray so long-running compute jobs are never accidentally interrupted.

### 3. ✨ Modern Edge WebView2 & CustomTkinter Hypervisors
- **Microsoft Edge WebView2**: Glassmorphic, dark-mode desktop interface powered by native Chromium / Edge runtime.
- **CustomTkinter Native Fallback**: Full high-comfort native dark UI if running on environments without WebView2.
- **Zero-Friction Local Loopback**: Embedded HTTP bridge (`http://127.0.0.1:48123/ui`) accessible directly in any browser.

### 4. 💰 Live Revenue & Session Metering Ticker
Complete transparency over your hosting earnings:
- **Live Session Timer**: Tracks uninterrupted uptime down to the second.
- **Real-Time Earnings Ticker**: Accumulates session revenue continuously based on your active compute rate (e.g. $0.50/hr).
- **Active Pod Counter**: Displays exact number of tenant workloads currently running.

### 5. 🛡️ Host-Determined Memory & Space Allocation
You decide exactly how much of your computer to share:
- **Dedicated RAM Limit (GB)**: Adjust the slider to set your maximum allocated memory. The host operating system automatically reserves a safe buffer so your PC never slows down or freezes.
- **Scratch Disk Storage Limit (GB)**: Cap the maximum disk space allocated for workloads. The active disk quota watcher immediately aborts tasks that attempt to exceed your storage limit.
- **CPU Thread Allocation**: Choose how many logical processor cores to dedicate.
- **Kernel Cgroup Containment**: Enforces `--memory`, `--memory-swap`, and `--cpus` limits at the container level.

### 6. 🔒 Zero-Persistence Sandbox & Emergency Stop
- Workloads execute in isolated Docker containers with zero access to your personal files or host directories.
- All scratch data is placed in ephemeral directories (`~/.productify/pods/<instance_id>`).
- Upon termination, scratch storage undergoes cryptographic zero-overwrite before unlinking.
- **1-Click Emergency Stop & Wipe**: Instantly force-kills all running containers and purges all scratch disks.

---

## 🏗️ Architecture

```
                  ┌────────────────────────────────────────┐
                  │       Productify Web Marketplace       │
                  │        (https://productifynow.com)     │
                  └───────────────────▲────────────────────┘
                                      │
                         Outbound WebSocket / HTTP
                               Reverse Tunnel
                                      │
  ┌───────────────────────────────────▼───────────────────────────────────┐
  │                           PRODUCTIFY NODE                             │
  │                                                                       │
  │   ┌─────────────────────┐   ┌─────────────────┐   ┌───────────────┐   │
  │   │  Edge WebView2 /    │   │   System Tray   │   │ Thermal Guard │   │
  │   │  CustomTkinter UI   │   │ (pystray/pillow)│   │  (Safe 75°C)  │   │
  │   └──────────┬──────────┘   └────────┬────────┘   └───────┬───────┘   │
  │              │                       │                    │           │
  │              ▼                       ▼                    ▼           │
  │   ┌───────────────────────────────────────────────────────────────┐   │
  │   │        State Controller (LIVE 🟢 / PAUSED ⏸️)                 │   │
  │   └───────────────────────────────┬───────────────────────────────┘   │
  │                                   │                                   │
  │                                   ▼                                   │
  │   ┌───────────────────────────────────────────────────────────────┐   │
  │   │   Boundary & Quota Enforcer (RAM, Disk, CPU Limits)           │   │
  │   └───────────────────────────────┬───────────────────────────────┘   │
  │                                   │                                   │
  │              ┌────────────────────┴───────────────────┐               │
  │              ▼                                        ▼               │
  │   ┌───────────────────────┐               ┌───────────────────────┐   │
  │   │  Docker Host Engine   │               │ Direct Hardware Probe │   │
  │   │ (--gpus, --memory)    │               │ (nvidia-smi, RAM/CPU) │   │
  │   └───────────────────────┘               └───────────────────────┘   │
  └───────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (Python 3.12 recommended).
- *(Optional)* [Docker Desktop](https://www.docker.com/) for isolated GPU container sandboxing.

### Install Dependencies
```bash
py -m pip install -r requirements.txt
```

### 1. Launching on Windows
Double-click `scripts\run_gui.bat` or run in PowerShell / Command Prompt:
```powershell
py main.py
```

### 2. Launching with Custom Options
```powershell
# Set Thermal Guard maximum temperature ceiling to 72°C
py main.py --max-temp 72

# Force CustomTkinter dark UI
py main.py --ui ctk

# Force Microsoft Edge WebView2 GUI
py main.py --ui webview
```

### 3. Headless Server Mode (CLI / Mining Rigs)
To run on remote Linux servers or dedicated mining rigs without a window display:
```bash
py main.py --headless --token="YOUR_PAIRING_TOKEN" --ram=8.0 --disk=50.0 --live
```
*(System Tray and Thermal Guard remain fully operational in background!)*

---

## 🧪 Testing & Verification

Run the comprehensive unit test suite:
```bash
py -m unittest discover tests
```

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
