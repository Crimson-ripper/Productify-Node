"""Outbound reverse tunnel daemon connecting host node to Productify Cloud Relay."""

import json
import time
import threading
import urllib.request
import urllib.error
import logging
from productify_node.config import config
from productify_node.state import node_state
from productify_node.container import container_mgr

logger = logging.getLogger("productify_node.tunnel")


class ReverseTunnelDaemon:
    """Maintains outbound long-poll and WebSocket reverse tunnel to Productify Cloud Relay."""

    def __init__(self):
        self._thread = None
        self._running = False
        self._connected = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logger.info("Reverse tunnel background daemon started.")

    def stop(self):
        self._running = False
        self._connected = False
        node_state.tunnel_connected = False

    def _worker_loop(self):
        while self._running:
            # Respect LIVE / PAUSE state
            if not node_state.is_live:
                if self._connected:
                    self._connected = False
                    node_state.tunnel_connected = False
                    node_state.log("Tunnel suspended (Node is in PAUSED state).", "INFO")
                time.sleep(1.0)
                continue

            rental_id = config.get("rental_id")
            if not rental_id:
                time.sleep(2.0)
                continue

            base_url = config.get("platform_url", "https://productifynow.com").rstrip("/")
            poll_url = f"{base_url}/api/tunnel/host/{rental_id}/poll"

            try:
                data_bytes = json.dumps({"node_id": config.node_id}).encode("utf-8")
                req = urllib.request.Request(
                    poll_url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json", "User-Agent": "Productify-Node-Client/1.0"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    if resp.status == 200:
                        if not self._connected:
                            self._connected = True
                            node_state.tunnel_connected = True
                            node_state.log(f"Tunnel connected to relay: {poll_url}", "INFO")

                        node_state.record_heartbeat()
                        body = json.loads(resp.read().decode())
                        messages = body.get("messages", [])
                        for msg in messages:
                            self._dispatch_rpc(msg, base_url, rental_id)
            except urllib.error.HTTPError as e:
                # 404 means rental node is not registered yet on platform
                self._connected = False
                node_state.tunnel_connected = False
                time.sleep(4.0)
            except Exception as e:
                self._connected = False
                node_state.tunnel_connected = False
                time.sleep(3.0)

    def _dispatch_rpc(self, msg, base_url, rental_id):
        """Execute received RPC action and reply to cloud relay."""
        msg_id = msg.get("id")
        action = msg.get("action")
        payload = msg.get("payload", {})

        node_state.log(f"Received RPC task '{action}' (ID: {msg_id})", "INFO")
        reply_data = {"msg_id": msg_id, "ok": True}

        try:
            if action == "deploy_pod":
                res = container_mgr.start_pod(
                    instance_id=payload.get("instance_id", "default"),
                    docker_image=payload.get("docker_image", "python:3.11-slim"),
                )
                reply_data.update(res)

            elif action == "exec":
                res = container_mgr.exec_in_pod(
                    instance_id=payload.get("instance_id"),
                    command=payload.get("command"),
                    code=payload.get("code"),
                )
                reply_data.update(res)

            elif action == "destroy_pod":
                res = container_mgr.destroy_pod(payload.get("instance_id"))
                reply_data.update(res)

            else:
                reply_data = {"msg_id": msg_id, "ok": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            reply_data = {"msg_id": msg_id, "ok": False, "error": str(e)}

        # Send reply back across the tunnel
        reply_url = f"{base_url}/api/tunnel/host/{rental_id}/reply"
        try:
            req = urllib.request.Request(
                reply_url,
                data=json.dumps(reply_data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8):
                pass
            node_state.log(f"Replied to RPC task '{action}' successfully", "INFO")
        except Exception as e:
            logger.warning(f"Failed to post RPC reply: {e}")


tunnel_daemon = ReverseTunnelDaemon()
