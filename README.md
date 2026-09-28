# ⚡ Productify Node

> **Official Desktop Client & Host Hypervisor for Physical GPU & Compute Providers on [Productify](https://productifynow.com).**

Productify Node connects your physical computer (and NVIDIA GPU) directly to the Productify global compute marketplace across any home router, NAT, or firewall without port forwarding.

Renters deploy containerized deep learning workloads and Python tasks on your machine, while **you maintain 100% control over hardware boundaries, live availability, and data security.**

---

## 🌟 Key Features

### 1. 🛡️ Host-Determined Memory & Space Allocation
You decide exactly how much of your computer to share. Workloads are strictly restricted to perform within your predetermined boundaries:
- **Dedicated RAM Limit (GB)**: Adjust the slider to set your maximum allocated memory. The host operating system automatically reserves a safe buffer so your PC never slows down or freezes.
- **Scratch Disk Storage Limit (GB)**: Cap the maximum disk space allocated for workloads. The active disk quota watcher immediately aborts tasks that attempt to exceed your storage limit.
- **CPU Thread Allocation**: Choose how many logical processor cores to dedicate.
- **Docker Cgroup Containment**: Enforces `--memory`, `--memory-swap`, and `--cpus` limits at the kernel level.

### 2. 🟢 Live / Pause Availability Switch
Take control of when your machine works:
- **LIVE (Online & Earning)**: Node connects outbound to the cloud relay, appears as available on the marketplace, and accepts incoming container workloads.
- **PAUSED (Offline / Sleep)**: Instantly suspends the reverse tunnel, marks your node offline on the marketplace, and prevents any new workloads from running.

### 3. 🔑 System Authentication & Seamless Pairing
- Persistent hardware fingerprinting uniquely identifies your machine.
- 1-Click Browser Pairing via local loopback bridge (`http://127.0.0.1:48123/probe`).
- Input your Host Pairing Token directly from the Productify Seller Dashboard.

### 4. 📊 Real-Time Hardware Telemetry
- Direct physical NVIDIA GPU probe via `nvidia-smi` and NVML (Model, VRAM Used / Total, GPU Temperature, Driver Version).
- CPU core usage and active threads.
- Physical RAM vs. Bounded Allocation meters.
- Storage free vs. Bounded Scratch meters.

### 5. 🔒 Zero-Persistence Sandbox & Emergency Stop
- Workloads execute in isolated Docker containers with zero access to your personal files or host directories.
- All scratch data is placed in ephemeral directories (`~/.productify/pods/<instance_id>`).
- Upon termination, scratch storage undergoes cryptographic zero-overwrite before unlinking (`shutil.rmtree`).
- **1-Click Emergency Stop & Wipe**: Instantly force-kills all running containers and cleans all scratch disks.

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
  │   ┌─────────────────────┐                 ┌───────────────────────┐   │
  │   │  Native Desktop GUI │                 │  Local Loopback HTTP  │   │
  │   │   (Tkinter Dark)    │                 │   (127.0.0.1:48123)   │   │
  │   └──────────┬──────────┘                 └───────────┬───────────┘   │
  │              │                                        │               │
  │              ▼                                        ▼               │
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
- **Python 3.10+** (Python's built-in standard library powers the entire application — zero mandatory external dependencies!).
- *(Optional)* [Docker Desktop](https://www.docker.com/) for isolated GPU container sandboxing.

### 1. Launching on Windows
Double-click `scripts\run_gui.bat` or run in PowerShell / Command Prompt:
```powershell
python main.py
```
*(If `python` is not in your PATH, run `py main.py`)*

### 2. Launching on Linux / macOS
```bash
chmod +x scripts/run_gui.sh
./scripts/run_gui.sh
```

### 3. Headless Server Mode (CLI / Mining Rigs)
To run on remote Linux servers or mining rigs without a GUI display:
```bash
python main.py --headless --token="YOUR_PAIRING_TOKEN" --ram=8.0 --disk=50.0 --live
```

---

## 🖥️ User Interface Overview

| Tab | Purpose |
| :--- | :--- |
| **📊 Hardware Dashboard** | Real-time telemetry cards for GPU (VRAM/Temp/Driver), CPU cores, RAM, and Disk free space. |
| **🛡️ Memory & Space Allocation** | Interactive sliders to set hard RAM limits, scratch disk quotas, and CPU core counts. |
| **🔑 System Authentication** | Enter pairing token, link your Productify account, and verify platform reachability. |
| **📋 Active Pods & Logs** | Live audit stream, active container monitor, and 1-Click Emergency Stop & Wipe button. |

---

## 🧪 Testing & Verification

Run the built-in test suite:
```bash
python -m unittest discover tests
```

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
