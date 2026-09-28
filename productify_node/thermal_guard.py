"""Hardware Thermal Protection Guard for Productify Node.

Continuously monitors physical GPU temperatures and automatically throttles
or pauses node workloads if temperatures exceed user or hardware safe thresholds.
Guarantees host hardware safety under high-compute workloads.
"""

import time
import threading
import logging
from productify_node.telemetry import probe_gpu
from productify_node.state import node_state

logger = logging.getLogger("productify_node.thermal_guard")


class ThermalGuard:
    """Active background daemon protecting host GPU & CPU against thermal stress."""

    def __init__(self, max_temp_c=75, warning_temp_c=70, cooldown_target_c=62, interval=5):
        self.max_temp_c = max_temp_c
        self.warning_temp_c = warning_temp_c
        self.cooldown_target_c = cooldown_target_c
        self.interval = interval

        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        self.last_temp = 0
        self.is_overheated = False
        self.status = "NORMAL"  # NORMAL, WARNING, CRITICAL_PAUSED, COOLDOWN
        self.overheat_count = 0
        self._warned = False

    def start(self):
        """Start thermal guard background monitoring thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ThermalGuard")
            self._thread.start()
            logger.info(f"Thermal Guard active (Max Temp: {self.max_temp_c}°C, Cooldown: {self.cooldown_target_c}°C).")

    def stop(self):
        """Stop background monitoring."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def set_limits(self, max_temp=None, warning_temp=None, cooldown_temp=None):
        """Dynamically update thermal safety bounds."""
        with self._lock:
            if max_temp is not None:
                self.max_temp_c = int(max_temp)
            if warning_temp is not None:
                self.warning_temp_c = int(warning_temp)
            if cooldown_temp is not None:
                self.cooldown_target_c = int(cooldown_temp)
        logger.info(f"Thermal bounds updated: Max={self.max_temp_c}°C, Warn={self.warning_temp_c}°C")

    def get_status(self):
        """Return current thermal health and safety metrics."""
        return {
            "enabled": self._running,
            "current_temp_c": self.last_temp,
            "max_temp_c": self.max_temp_c,
            "warning_temp_c": self.warning_temp_c,
            "cooldown_target_c": self.cooldown_target_c,
            "status": self.status,
            "is_overheated": self.is_overheated,
            "overheat_events": self.overheat_count,
        }

    def check_once(self):
        """Perform a single thermal evaluation (useful for test suites and manual triggers)."""
        gpu = probe_gpu()
        if not gpu.get("available", False):
            self.last_temp = 0
            self.status = "NORMAL"
            return self.get_status()

        temp = int(gpu.get("temperature_c", 0))
        self.last_temp = temp

        if temp >= self.max_temp_c:
            if not self.is_overheated:
                self.is_overheated = True
                self.status = "CRITICAL_PAUSED"
                self.overheat_count += 1
                msg = (
                    f"⚠️ [THERMAL GUARD] CRITICAL OVERHEAT: GPU at {temp}°C exceeds safety ceiling "
                    f"({self.max_temp_c}°C)! Auto-pausing node to protect host hardware."
                )
                logger.error(msg)
                node_state.log(msg, level="ERROR")
                node_state.set_paused()
            else:
                self.status = "CRITICAL_PAUSED"
        elif self.is_overheated:
            if temp <= self.cooldown_target_c:
                self.is_overheated = False
                self.status = "NORMAL"
                self._warned = False
                msg = (
                    f"❄️ [THERMAL GUARD] GPU cooled down to {temp}°C (below {self.cooldown_target_c}°C). "
                    f"Hardware normalized. Ready to resume workloads."
                )
                logger.info(msg)
                node_state.log(msg, level="INFO")
            else:
                self.status = "COOLDOWN"
        elif temp >= self.warning_temp_c:
            self.status = "WARNING"
            if not self._warned:
                self._warned = True
                msg = f"🌡️ [THERMAL GUARD] High GPU temperature: {temp}°C approaching limit ({self.max_temp_c}°C)."
                logger.warning(msg)
                node_state.log(msg, level="WARNING")
        else:
            self.status = "NORMAL"
            self._warned = False

        return self.get_status()

    def _monitor_loop(self):
        while self._running:
            try:
                self.check_once()
            except Exception as e:
                logger.warning(f"Error in thermal monitor probe: {e}")
            time.sleep(self.interval)


thermal_guard = ThermalGuard()
