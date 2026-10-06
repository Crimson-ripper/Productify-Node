"""Cloud gaming streaming hypervisor and Sunshine controller module."""

from productify_node.streaming.sunshine_mgr import sunshine_mgr
from productify_node.streaming.diagnostics import run_diagnostics
from productify_node.streaming.installer import INSTALL_STATE, start_installation_async, run_full_installation_sync
from productify_node.streaming.game_detector import find_game_executable, launch_game, stop_game
from productify_node.streaming.input_injector import injector
from productify_node.streaming.webrtc_streamer import webrtc_streamer

__all__ = [
    "sunshine_mgr",
    "run_diagnostics",
    "INSTALL_STATE",
    "start_installation_async",
    "run_full_installation_sync",
    "find_game_executable",
    "launch_game",
    "stop_game",
    "injector",
    "webrtc_streamer",
]
