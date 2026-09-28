"""Configuration and state persistence manager for Productify Node."""

import os
import json
import uuid
import platform
import logging

logger = logging.getLogger("productify_node.config")

CONFIG_DIR = os.path.expanduser(os.path.join("~", ".productify"))
CONFIG_FILE = os.path.join(CONFIG_DIR, "node_config.json")
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "credentials.json")


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


class NodeConfig:
    """Manages local host node configuration, pairing tokens, and resource limits."""

    DEFAULT_SETTINGS = {
        "node_id": None,
        "node_name": platform.node() or "Productify-Host-Node",
        "platform_url": "https://productifynow.com",
        "pairing_token": "",
        "rental_id": "",
        "is_live": False,
        "ram_limit_gb": 2.0,
        "disk_limit_gb": 25.0,
        "cpu_limit_cores": max(1, (os.cpu_count() or 4) - 1),
        "enable_gpu": True,
        "auto_start_tunnel": True,
        "enforce_strict_boundaries": True,
        "local_bridge_port": 48123,
    }

    def __init__(self):
        ensure_config_dir()
        self.data = dict(self.DEFAULT_SETTINGS)
        self.load()

        # Ensure persistent node_id
        if not self.data.get("node_id"):
            self.data["node_id"] = f"node-{uuid.uuid4().hex[:12]}"
            self.save()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
            except Exception as e:
                logger.warning(f"Could not load config file {CONFIG_FILE}: {e}")

    def save(self):
        ensure_config_dir()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, auto_save=True):
        self.data[key] = value
        if auto_save:
            self.save()

    def update(self, mapping, auto_save=True):
        self.data.update(mapping)
        if auto_save:
            self.save()

    @property
    def node_id(self):
        return self.data.get("node_id")

    @property
    def is_live(self):
        return bool(self.data.get("is_live", False))

    @is_live.setter
    def is_live(self, val):
        self.set("is_live", bool(val))

    @property
    def ram_limit_gb(self):
        return float(self.data.get("ram_limit_gb", 2.0))

    @ram_limit_gb.setter
    def ram_limit_gb(self, val):
        self.set("ram_limit_gb", float(val))

    @property
    def disk_limit_gb(self):
        return float(self.data.get("disk_limit_gb", 25.0))

    @disk_limit_gb.setter
    def disk_limit_gb(self, val):
        self.set("disk_limit_gb", float(val))

    @property
    def cpu_limit_cores(self):
        return int(self.data.get("cpu_limit_cores", 2))

    @cpu_limit_cores.setter
    def cpu_limit_cores(self, val):
        self.set("cpu_limit_cores", int(val))


config = NodeConfig()
