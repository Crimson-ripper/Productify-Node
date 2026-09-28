"""Global node state machine and event listener bus."""

import time
import logging
from productify_node.config import config

logger = logging.getLogger("productify_node.state")


class NodeState:
    """Manages runtime status, LIVE/PAUSED state toggling, and event broadcasting."""

    def __init__(self):
        self._status = "LIVE" if config.is_live else "PAUSED"
        self._active_pods = {}
        self._log_history = []
        self._listeners = []
        self._log_listeners = []
        self._tunnel_connected = False
        self._last_heartbeat = None

    @property
    def status(self):
        return self._status

    @property
    def is_live(self):
        return self._status == "LIVE"

    @property
    def is_paused(self):
        return self._status == "PAUSED"

    @property
    def tunnel_connected(self):
        return self._tunnel_connected

    @tunnel_connected.setter
    def tunnel_connected(self, val):
        self._tunnel_connected = bool(val)
        self._notify_listeners()

    def set_live(self):
        """Set node to LIVE (advertising to marketplace, active tunnel)."""
        self._status = "LIVE"
        config.is_live = True
        self.log("Node status switched to LIVE. Accepting marketplace workloads.", level="INFO")
        self._notify_listeners()

    def set_paused(self):
        """Set node to PAUSED (suspended tunnel, idle and safe)."""
        self._status = "PAUSED"
        config.is_live = False
        self.log("Node status switched to PAUSED. Tunnel suspended. Machine safe.", level="INFO")
        self._notify_listeners()

    def toggle_live_pause(self):
        """Toggle between LIVE and PAUSED."""
        if self.is_live:
            self.set_paused()
        else:
            self.set_live()
        return self._status

    def record_heartbeat(self):
        self._last_heartbeat = time.time()
        self._notify_listeners()

    def add_pod(self, instance_id, pod_info):
        self._active_pods[instance_id] = pod_info
        self.log(f"Pod allocated: {instance_id} (Image: {pod_info.get('image', 'default')})", level="INFO")
        self._notify_listeners()

    def remove_pod(self, instance_id):
        if instance_id in self._active_pods:
            del self._active_pods[instance_id]
            self.log(f"Pod removed & scratch data wiped: {instance_id}", level="INFO")
            self._notify_listeners()

    def get_active_pods(self):
        return dict(self._active_pods)

    def log(self, text, level="INFO"):
        """Add timestamped entry to internal audit log and notify UI."""
        timestamp = time.strftime("%H:%M:%S")
        entry = {"time": timestamp, "text": text, "level": level}
        self._log_history.append(entry)
        if len(self._log_history) > 500:
            self._log_history = self._log_history[-500:]

        # Notify log listeners
        for cb in list(self._log_listeners):
            try:
                cb(entry)
            except Exception as e:
                logger.debug(f"Error in log listener: {e}")

    def get_logs(self, limit=100):
        return self._log_history[-limit:]

    def add_listener(self, callback):
        """Register state change listener (called when status/pods/tunnel change)."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def add_log_listener(self, callback):
        """Register listener for new log entries."""
        if callback not in self._log_listeners:
            self._log_listeners.append(callback)

    def _notify_listeners(self):
        for cb in list(self._listeners):
            try:
                cb(self)
            except Exception as e:
                logger.debug(f"Error in state listener: {e}")


node_state = NodeState()
