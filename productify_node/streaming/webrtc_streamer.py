"""Real-time WebRTC Cloud Game Streaming Server for Productify Node.

Captures game display at low latency, encodes H.264, and streams directly
to web browsers (Laptop B) via standard WebRTC, while processing remote
mouse, keyboard, and controller inputs.
"""

import os
import sys
import json
import time
import asyncio
import fractions
import threading
import logging
import mss
import av
import numpy as np

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
    RTCIceServer,
    RTCConfiguration,
    VideoStreamTrack,
)
from productify_node.streaming.input_injector import injector
from productify_node.state import node_state

logger = logging.getLogger("productify_node.webrtc")

# Google STUN for seamless cross-network NAT traversal
STUN_SERVERS = [
    RTCIceServer(urls="stun:stun.l.google.com:19302"),
    RTCIceServer(urls="stun:stun1.l.google.com:19302"),
]
RTC_CONFIG = RTCConfiguration(iceServers=STUN_SERVERS)


class ScreenCaptureTrack(VideoStreamTrack):
    """High-performance video track capturing desktop / game window frames at 60 FPS."""

    kind = "video"

    def __init__(self, fps=60):
        super().__init__()
        self.fps = fps
        self.time_base = fractions.Fraction(1, fps)
        self._timestamp = 0
        self._start_time = None
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1] if len(self.sct.monitors) > 1 else self.sct.monitors[0]

        # Downscale target if monitor is 4K or ultra wide for optimum bandwidth
        self.target_width = 1280
        self.target_height = 720
        logger.info(f"Initialized ScreenCaptureTrack: monitor={self.monitor['width']}x{self.monitor['height']} -> {self.target_width}x{self.target_height} @ {self.fps}FPS")

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        # Grab raw BGRA desktop buffer
        # Run in thread pool to avoid blocking asyncio event loop
        loop = asyncio.get_event_loop()
        raw_img = await loop.run_in_executor(None, self.sct.grab, self.monitor)

        # Convert to numpy array (BGRA)
        img_np = np.frombuffer(raw_img.raw, dtype=np.uint8).reshape((raw_img.height, raw_img.width, 4))

        # Fast subsampling / cropping to 16:9 720p
        if raw_img.width != self.target_width or raw_img.height != self.target_height:
            step_y = raw_img.height / self.target_height
            step_x = raw_img.width / self.target_width
            y_indices = (np.arange(self.target_height) * step_y).astype(int)
            x_indices = (np.arange(self.target_width) * step_x).astype(int)
            sampled = img_np[y_indices[:, None], x_indices]
        else:
            sampled = img_np

        # Wrap in PyAV VideoFrame (bgra format)
        frame = av.VideoFrame.from_ndarray(sampled, format="bgra")
        frame.pts = pts
        frame.time_base = time_base

        return frame

    async def next_timestamp(self):
        if self._start_time is None:
            self._start_time = time.time()
            self._timestamp = 0
        else:
            self._timestamp += 1
            # Rate limit to target FPS
            expected_time = self._start_time + (self._timestamp / self.fps)
            now = time.time()
            if expected_time > now:
                await asyncio.sleep(expected_time - now)

        return self._timestamp, self.time_base

    def stop(self):
        super().stop()
        try:
            self.sct.close()
        except Exception:
            pass


class WebRTCStreamServer:
    """Manages active WebRTC cloud gaming sessions and signaling on Laptop A."""

    def __init__(self):
        self.active_pcs = {}
        self.active_tracks = {}
        self._loop = None
        self._thread = None
        self._ready_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=3.0)

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready_event.set()
        logger.info("WebRTC Stream Server async loop started.")
        self._loop.run_forever()

    def handle_offer_sync(self, session_id, sdp_dict):
        """Thread-safe synchronous wrapper for processing SDP Offer."""
        if not self._loop or not self._loop.is_running():
            self.start()

        future = asyncio.run_coroutine_threadsafe(
            self.handle_offer(session_id, sdp_dict),
            self._loop
        )
        return future.result(timeout=10.0)

    async def handle_offer(self, session_id, sdp_dict):
        """Create RTCPeerConnection, attach ScreenCaptureTrack, and return SDP Answer."""
        # Clean up existing PC for session
        await self.close_session(session_id)

        pc = RTCPeerConnection(configuration=RTC_CONFIG)
        track = ScreenCaptureTrack(fps=60)
        pc.addTrack(track)

        self.active_pcs[session_id] = pc
        self.active_tracks[session_id] = track

        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(f"WebRTC DataChannel '{channel.label}' established for session {session_id}")

            @channel.on("message")
            def on_message(message):
                try:
                    event = json.loads(message)
                    injector.dispatch(event)
                except Exception as e:
                    logger.debug(f"DataChannel parse error: {e}")

        @pc.on("connectionstatechange")
        async def on_state_change():
            logger.info(f"Session {session_id} WebRTC state: {pc.connectionState}")
            if pc.connectionState in ["failed", "closed"]:
                await self.close_session(session_id)

        # Set remote description
        offer = RTCSessionDescription(sdp=sdp_dict["sdp"], type=sdp_dict["type"])
        await pc.setRemoteDescription(offer)

        # Generate answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        node_state.log(f"Generated WebRTC SDP Answer for session {session_id}", "INFO")

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
        }

    def add_ice_candidate_sync(self, session_id, candidate_dict):
        if not self._loop or not self._loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(
            self.add_ice_candidate(session_id, candidate_dict),
            self._loop
        )

    async def add_ice_candidate(self, session_id, candidate_dict):
        pc = self.active_pcs.get(session_id)
        if not pc:
            return

        cand = candidate_dict.get("candidate")
        sdp_mid = candidate_dict.get("sdpMid")
        sdp_mline_index = candidate_dict.get("sdpMLineIndex")

        if cand:
            try:
                candidate = RTCIceCandidate(
                    candidate=cand,
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index,
                )
                await pc.addIceCandidate(candidate)
            except Exception as e:
                logger.debug(f"ICE candidate add error: {e}")

    def close_session_sync(self, session_id):
        if not self._loop or not self._loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(
            self.close_session(session_id),
            self._loop
        )
        try:
            return future.result(timeout=3.0)
        except Exception:
            return None

    async def close_session(self, session_id):
        track = self.active_tracks.pop(session_id, None)
        if track:
            track.stop()

        pc = self.active_pcs.pop(session_id, None)
        if pc:
            try:
                await pc.close()
            except Exception:
                pass
            logger.info(f"Closed WebRTC session {session_id}")


webrtc_streamer = WebRTCStreamServer()
# Start background event loop eagerly
webrtc_streamer.start()
