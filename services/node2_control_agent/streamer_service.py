from __future__ import annotations

import signal
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from agents.node2.node2_streamer_controller import PROFILES, build_gstreamer_command


@dataclass
class StreamStatus:
    running: bool = False
    profile: Optional[str] = None
    node1_ip: Optional[str] = None
    port: int = 5000
    device: str = "/dev/video0"
    pid: Optional[int] = None
    started_at: Optional[float] = None
    message: str = "idle"
    transport: str = "rtp"


class StreamerService:
    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.status = StreamStatus()

    def profiles(self):
        return PROFILES

    def get_status(self) -> StreamStatus:
        if self.proc is not None and self.proc.poll() is not None:
            self.status.running = False
            self.status.message = f"streamer exited rc={self.proc.returncode}"
            self.status.pid = None
            self.proc = None
        return self.status

    def _build_command(self, node1_ip: str, port: int, profile: str, device: str, transport: str) -> list[str]:
        if transport == "rtp":
            return build_gstreamer_command(profile=profile, node1_ip=node1_ip, port=port, device=device)
        if transport == "timed_jpeg_udp":
            return [
                sys.executable,
                "-m",
                "agents.node2.node2_timed_jpeg_sender",
                "--node1-ip", node1_ip,
                "--port", str(port),
                "--profile", profile,
                "--device", device,
            ]
        raise ValueError(f"Unknown transport: {transport}")

    def start(self, node1_ip: str, port: int, profile: str, device: str = "/dev/video0", transport: str = "rtp") -> StreamStatus:
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile: {profile}")
        if transport == "timed_jpeg_udp" and PROFILES[profile].get("kind") != "mjpeg":
            raise ValueError("timed_jpeg_udp transport currently supports MJPEG profiles only")
        if self.get_status().running:
            self.stop()
        cmd = self._build_command(node1_ip=node1_ip, port=port, profile=profile, device=device, transport=transport)
        self.proc = subprocess.Popen(cmd)
        self.status = StreamStatus(True, profile, node1_ip, port, device, self.proc.pid, time.time(), "running", transport)
        return self.status

    def stop(self) -> StreamStatus:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            time.sleep(1)
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.status.running = False
        self.status.pid = None
        self.status.message = "stopped"
        return self.status

    def switch_profile(self, profile: str) -> StreamStatus:
        current = self.get_status()
        if not current.node1_ip:
            raise RuntimeError("No active or previous node1_ip; call start first")
        return self.start(current.node1_ip, current.port, profile, current.device, current.transport)


streamer_service = StreamerService()
