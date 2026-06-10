from __future__ import annotations

import signal
import subprocess
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

    def start(self, node1_ip: str, port: int, profile: str, device: str = "/dev/video0") -> StreamStatus:
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile: {profile}")
        if self.get_status().running:
            self.stop()
        cmd = build_gstreamer_command(profile=profile, node1_ip=node1_ip, port=port, device=device)
        self.proc = subprocess.Popen(cmd)
        self.status = StreamStatus(True, profile, node1_ip, port, device, self.proc.pid, time.time(), "running")
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
        return self.start(current.node1_ip, current.port, profile, current.device)


streamer_service = StreamerService()
