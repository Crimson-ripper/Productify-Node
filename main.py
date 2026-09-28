#!/usr/bin/env python3
"""Productify Node — Physical GPU & Compute Provider Desktop Application & Daemon.

Usage:
  py main.py               # Launch Native Desktop GUI
  py main.py --headless    # Launch Headless Server Daemon
"""

import sys
import time
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("productify_node")


def main():
    parser = argparse.ArgumentParser(description="Productify Node — Physical Compute & GPU Provider Client")
    parser.add_argument("--headless", action="store_true", help="Run in headless daemon mode (no GUI window)")
    parser.add_argument("--token", type=str, help="Pairing token from Productify Seller Dashboard")
    parser.add_argument("--rental-id", type=str, help="Assigned rental ID")
    parser.add_argument("--ram", type=float, help="Predetermined RAM limit in GB")
    parser.add_argument("--disk", type=float, help="Predetermined Disk scratch limit in GB")
    parser.add_argument("--live", action="store_true", help="Immediately set node to LIVE state upon startup")
    parser.add_argument("--port", type=int, default=48123, help="Local bridge server port (default: 48123)")

    args = parser.parse_args()

    from productify_node.config import config
    from productify_node.state import node_state
    from productify_node.boundary import enforcer
    from productify_node.bridge.local_server import local_bridge
    from productify_node.tunnel import tunnel_daemon

    # Apply command-line overrides
    if args.token:
        config.set("pairing_token", args.token)
    if args.rental_id:
        config.set("rental_id", args.rental_id)
    if args.ram or args.disk:
        enforcer.set_allocations(
            ram_gb=args.ram or config.ram_limit_gb,
            disk_gb=args.disk or config.disk_limit_gb
        )
    if args.live:
        node_state.set_live()

    if args.headless:
        logger.info("=" * 60)
        logger.info("⚡ PRODUCTIFY NODE — HEADLESS DAEMON MODE")
        logger.info("=" * 60)
        logger.info(f"Node ID          : {config.node_id}")
        logger.info(f"Initial Status   : {node_state.status}")
        logger.info(f"RAM Allocation   : {config.ram_limit_gb} GB")
        logger.info(f"Disk Allocation  : {config.disk_limit_gb} GB")
        logger.info(f"Local Loopback   : http://127.0.0.1:{args.port}/probe")
        logger.info("Press Ctrl+C to stop.")
        logger.info("=" * 60)

        local_bridge.port = args.port
        local_bridge.start()
        tunnel_daemon.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping Productify Node daemon...")
            local_bridge.stop()
            tunnel_daemon.stop()
    else:
        # Launch Desktop GUI
        from productify_node.gui.app import start_gui
        start_gui()


if __name__ == "__main__":
    main()
