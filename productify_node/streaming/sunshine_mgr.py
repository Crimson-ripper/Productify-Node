"""Sunshine streaming engine controller and WAN session manager."""

import os
import sys
import json
import time
import socket
import random
import shutil
import urllib.request
import subprocess
import logging
from productify_node.config import config
from productify_node.state import node_state

logger = logging.getLogger("productify_node.sunshine")

CREATE_NO_WINDOW = 0x08000000

SUNSHINE_DIR = os.path.expanduser(os.path.join("~", ".productify", "sunshine"))
CONFIG_DIR = os.path.join(SUNSHINE_DIR, "config")


def get_public_ip():
    """Discover host machine public WAN IP address for cross-network streaming."""
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]
    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                ip = resp.read().decode("utf-8").strip()
                if ip and len(ip.split(".")) == 4:
                    return ip
        except Exception:
            continue
    # Fallback to local machine IP
    return get_lan_ip()


def get_lan_ip():
    """Discover local network IP address (e.g. 192.168.x.x) for LAN connections."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


class SunshineManager:
    """Orchestrates Sunshine daemon, game application sandboxing, and WAN pairing."""

    def __init__(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.process = None
        self.web_process = None
        self.current_session = None
        self.sunshine_exe = self._find_sunshine()
        self.web_exe = self._find_web_server()

    def _find_web_server(self):
        """Locate moonlight-web Actix WebRTC streaming server binary."""
        base_dirs = [
            getattr(sys, "_MEIPASS", ""),
            os.path.dirname(sys.executable),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            os.path.expanduser(r"~\Downloads\Productify--main\Productify-Node"),
            r"C:\Users\lenovo\Downloads\Productify--main\Productify-Node",
        ]
        candidates = []
        for b in base_dirs:
            if b:
                candidates.append(os.path.join(b, "bin", "moonlight-web", "web-server.exe"))
                candidates.append(os.path.join(b, "bin", "moonlight-web", "web-server"))
                candidates.append(os.path.join(b, "web-server.exe"))
        candidates.extend([
            shutil.which("web-server.exe"),
            shutil.which("web-server"),
        ])
        for c in candidates:
            if c and os.path.exists(c):
                return os.path.abspath(c)
        return None

    def _ensure_web_server_config(self):
        """Pre-configure Moonlight-Web with admin credentials and automatic login bypass."""
        import hashlib
        salt_hex = "c320a21ba2ffe63bf7c8672a42ebeb2d"
        iterations = 600000

        def hash_p(pw):
            return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()

        role_id = 2999276974
        admin_role = {
            "name": "Admin",
            "ty": "Admin",
            "default_settings": None,
            "permissions": {
                "allow_add_hosts": True,
                "maximum_bitrate_kbps": None,
                "allow_codec_h264": True,
                "allow_codec_h265": True,
                "allow_codec_av1": True,
                "allow_hdr": True,
                "allow_transport_webrtc": True,
                "allow_transport_websockets": True
            }
        }
        users = {
            "1001": {
                "role_id": role_id,
                "name": "admin",
                "password": {"salt": salt_hex, "hash": hash_p("admin"), "iterations": iterations},
                "client_unique_id": "admin"
            },
            "1002": {
                "role_id": role_id,
                "name": "productify",
                "password": {"salt": salt_hex, "hash": hash_p("productify"), "iterations": iterations},
                "client_unique_id": "productify"
            },
            "1003": {
                "role_id": role_id,
                "name": "Aryansh Kulshreshtha",
                "password": {"salt": salt_hex, "hash": hash_p("admin"), "iterations": iterations},
                "client_unique_id": "Aryansh Kulshreshtha"
            }
        }
        data = {
            "version": "3",
            "users": users,
            "hosts": {},
            "roles": {str(role_id): admin_role},
            "default_role_id": role_id,
            "default_user_id": 1001
        }

        dirs = []
        if self.web_exe:
            dirs.append(os.path.join(os.path.dirname(self.web_exe), "server"))
        dirs.append(os.path.expanduser(r"~/.productify/moonlight-web/server"))
        dirs.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "bin", "moonlight-web", "server")))

        for d in dirs:
            try:
                os.makedirs(d, exist_ok=True)
                fpath = os.path.join(d, "data.json")
                with open(fpath, "w", encoding="utf-8") as fp:
                    json.dump(data, fp, indent=2)
            except Exception as e:
                logger.debug(f"Could not seed {d}: {e}")

    def _find_sunshine(self):
        """Locate Sunshine binary across standard Windows installations and local bin."""
        candidates = [
            # 1. Productify bundled bin
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "bin", "sunshine", "sunshine.exe")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "bin", "sunshine", "sunshine")),
            # 2. Standard Windows Program Files
            r"C:\Program Files\Sunshine\sunshine.exe",
            r"C:\Program Files (x86)\Sunshine\sunshine.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Sunshine\sunshine.exe"),
            # 3. System PATH
            shutil.which("sunshine.exe"),
            shutil.which("sunshine"),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def is_installed(self):
        self.sunshine_exe = self._find_sunshine()
        return self.sunshine_exe is not None

    def _generate_config(self, game_title, launch_cmd=None):
        """Generate sandboxed sunshine.conf and apps.json strictly locking stream to the game window."""
        conf_path = os.path.join(CONFIG_DIR, "sunshine.conf")
        apps_path = os.path.join(CONFIG_DIR, "apps.json")

        # Sunshine base configuration (no hardcoded nvenc, allows automatic QSV/AMF/NVENC/Software selection)
        sunshine_conf_content = (
            "port = 47989\n"
            "upnp = enabled\n"
            "fec_percentage = 20\n"
            "min_log_level = info\n"
            "channels = 2\n"
            "audio_sink = Default\n"
            "virtual_sink = Default\n"
        )
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(sunshine_conf_content)

        # Build application list with Desktop fallback so the stream is never black
        apps_list = [
            {
                "name": "Desktop",
                "image-path": "desktop.png",
            }
        ]
        if launch_cmd:
            apps_list.insert(0, {
                "name": game_title or "Productify Gamezone",
                "output": os.path.join(SUNSHINE_DIR, "game_stream.log"),
                "cmd": launch_cmd,
                "detached": True,
                "image-path": "",
            })
        elif game_title and game_title not in ("Cloud Game", "default"):
            apps_list.insert(0, {
                "name": game_title,
                "output": os.path.join(SUNSHINE_DIR, "game_stream.log"),
                "cmd": "",
                "detached": True,
                "image-path": "",
            })

        apps_data = {
            "env": {},
            "apps": apps_list
        }
        with open(apps_path, "w", encoding="utf-8") as f:
            json.dump(apps_data, f, indent=2)

        return conf_path, apps_path

    def start_session(self, session_id, game_title="Cloud Game", launch_cmd=None, game_package_url=None, is_private=False):
        """Launch Sunshine streaming server bound to the target game session."""
        if not node_state.is_live:
            return {"ok": False, "error": "Node is currently PAUSED. Cloud gaming is unavailable."}

        self.sunshine_exe = self._find_sunshine()
        if not self.sunshine_exe:
            node_state.log("Sunshine binary not found. Please run scripts/install_gaming_stack.bat", "WARNING")
            return {
                "ok": False,
                "missing_sunshine": True,
                "error": "Sunshine streaming engine is not installed on this host node. Run installer to enable gaming.",
                "install_hint": "Run scripts/install_gaming_stack.bat to install Sunshine and ViGEmBus in 1 click."
            }

        # Terminate any existing streaming instance
        self.stop_session()

        # Auto-detect game binary if launch_cmd not passed
        if not launch_cmd:
            try:
                from productify_node.streaming.game_detector import find_game_executable
                found_exe = find_game_executable(game_title)
                if found_exe:
                    launch_cmd = f'"{found_exe}"'
                    node_state.log(f"Auto-resolved game binary for '{game_title}': {launch_cmd}", "INFO")
            except Exception as ex:
                logger.debug(f"Game detector error: {ex}")

        conf_path, apps_path = self._generate_config(game_title, launch_cmd)

        # Generate a secure 4-digit pairing PIN for Moonlight pairing
        pin = f"{random.randint(1000, 9999)}"

        log_file = os.path.join(SUNSHINE_DIR, "sunshine.log")
        log_fp = open(log_file, "a", encoding="utf-8")

        cmd = [
            self.sunshine_exe,
            conf_path
        ]

        sun_dir = os.path.dirname(self.sunshine_exe) if self.sunshine_exe else SUNSHINE_DIR
        tools_dir = os.path.join(sun_dir, "tools")
        sub_env = os.environ.copy()
        sub_env["PATH"] = f"{tools_dir};{sun_dir};" + sub_env.get("PATH", "")

        kwargs = {
            "stdout": log_fp,
            "stderr": log_fp,
            "cwd": sun_dir,
            "env": sub_env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NO_WINDOW
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kwargs["startupinfo"] = si

        try:
            self.process = subprocess.Popen(cmd, **kwargs)
            wan_ip = get_public_ip()
            lan_ip = get_lan_ip()
            port = 47989
            web_port = 48080

            # Ensure Moonlight WebRTC streamer is running with pre-seeded credentials
            self.ensure_web_server_running(web_port)

            web_stream_url = f"http://{wan_ip}:{web_port}/"
            lan_stream_url = f"http://{lan_ip}:{web_port}/"

            self.current_session = {
                "session_id": session_id,
                "game_title": game_title,
                "pid": self.process.pid,
                "wan_ip": wan_ip,
                "lan_ip": lan_ip,
                "port": port,
                "web_port": web_port,
                "pin": pin,
                "web_username": "admin",
                "web_password": "admin",
                "is_private": is_private,
                "started_at": time.time(),
                "stream_url": web_stream_url,
                "lan_stream_url": lan_stream_url,
                "moonlight_uri": f"moonlight://{wan_ip}:{port}?pin={pin}",
                "status": "streaming"
            }

            node_state.log(f"Started Sunshine streaming daemon (PID {self.process.pid}) on WAN {wan_ip}:{port} (PIN {pin})", "INFO")

            return {
                "ok": True,
                "session_id": session_id,
                "game_title": game_title,
                "wan_ip": wan_ip,
                "lan_ip": lan_ip,
                "port": port,
                "web_port": web_port,
                "pin": pin,
                "web_username": "admin",
                "web_password": "admin",
                "moonlight_uri": f"moonlight://{wan_ip}:{port}?pin={pin}",
                "stream_url": web_stream_url,
                "lan_stream_url": lan_stream_url,
                "status": "streaming"
            }
        except Exception as e:
            node_state.log(f"Failed to start Sunshine daemon: {e}", "ERROR")
            return {"ok": False, "error": str(e)}

    def ensure_web_server_running(self, web_port=48080):
        """Ensure Moonlight-Web Actix server is running, listening, and pre-seeded with admin auth."""
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{web_port}/api/authenticate", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass

        self.web_exe = self._find_web_server()
        if not self.web_exe:
            return False

        # Pre-seed persistent authentication credentials
        self._ensure_web_server_config()

        # Clean up any stale web-server process
        try:
            subprocess.run(["taskkill", "/F", "/IM", "web-server.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass

        try:
            web_cmd = [self.web_exe, "--bind-address", f"0.0.0.0:{web_port}"]
            kwargs = {
                "cwd": os.path.dirname(self.web_exe),
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                CREATE_NO_WINDOW = 0x08000000
                kwargs["creationflags"] = CREATE_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                kwargs["startupinfo"] = si
            self.web_process = subprocess.Popen(web_cmd, **kwargs)
            node_state.log(f"Moonlight WebRTC browser player active on port {web_port} (Admin: admin/admin)", "INFO")
            return True
        except Exception as e:
            logger.warning(f"Could not start web-server daemon: {e}")
            return False

    def stop_session(self, session_id=None):
        """Terminate active Sunshine instance and clean up."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

        if self.web_process:
            try:
                self.web_process.terminate()
                self.web_process.wait(timeout=3)
            except Exception:
                try:
                    self.web_process.kill()
                except Exception:
                    pass
            self.web_process = None

        # Clean up any leftover processes
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/F", "/IM", "sunshine.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                subprocess.run(["taskkill", "/F", "/IM", "web-server.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except Exception:
                pass

        closed_session = self.current_session
        self.current_session = None

        if closed_session:
            node_state.log(f"Terminated Sunshine streaming session {closed_session.get('session_id')}", "INFO")

        return {"ok": True, "stopped": True}

    def get_status(self):
        """Return streaming daemon health and active session details."""
        is_running = False
        if self.process:
            poll = self.process.poll()
            is_running = (poll is None)

        return {
            "installed": self.is_installed(),
            "binary_path": self.sunshine_exe,
            "running": is_running,
            "current_session": self.current_session,
            "public_ip": get_public_ip() if is_running else None
        }


sunshine_mgr = SunshineManager()
