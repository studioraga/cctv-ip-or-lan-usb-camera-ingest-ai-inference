from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StartCameraRequest(BaseModel):
    node1_ip: str = Field(default_factory=lambda: __import__("os").getenv("AI_CAMERA_NODE1_IP", ""), min_length=1)
    port: int = Field(default=5000, ge=1, le=65535)
    profile: str = "mjpeg_720p30"
    device: str = "/dev/video0"
    transport: str = Field(default="rtp", pattern="^(rtp|timed_jpeg_udp)$")


class SwitchProfileRequest(BaseModel):
    profile: str


class CaptureSessionRequest(BaseModel):
    camera_id: str = Field(default_factory=lambda: __import__("os").getenv("AI_CAMERA_CAMERA_ID", "c922_node2_gate"), min_length=1)
    profile: str = "mjpeg_720p30"
    duration_sec: int = Field(default=60, ge=1, le=7200)
    device: str = "/dev/video0"
    transport: str = Field(default="timed_jpeg_udp", pattern="^timed_jpeg_udp$")
    udp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    dataset_mode: str = Field(default="source_jpeg", pattern="^source_jpeg$")
    frame_stride: int = Field(default=1, ge=1, le=3600)
    max_bytes: Optional[int] = Field(default=None, ge=1)
    requested_by: Optional[str] = Field(default="grafana", max_length=128)
    notes: str = Field(default="", max_length=1000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    camera_id: Optional[str] = None
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=1000)
