from __future__ import annotations

from typing import Any, Optional

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
    live_mp4: bool = False
    live_mp4_fps: float = Field(default_factory=lambda: float(__import__("os").getenv("AI_CAMERA_MOTION_STREAM_LIVE_MP4_FPS", "15")), ge=1.0, le=60.0)
    live_mp4_width: int = Field(default_factory=lambda: int(__import__("os").getenv("AI_CAMERA_MOTION_STREAM_LIVE_MP4_WIDTH", "640")), ge=160, le=1920)
    requested_by: Optional[str] = Field(default="grafana", max_length=128)
    notes: str = Field(default="", max_length=1000)


class MotionStreamRequest(BaseModel):
    camera_id: str = Field(default_factory=lambda: __import__("os").getenv("AI_CAMERA_CAMERA_ID", "c922_node2_gate"), min_length=1)
    profile: str = "mjpeg_720p30"
    duration_sec: int = Field(default_factory=lambda: int(__import__("os").getenv("AI_CAMERA_MOTION_STREAM_DURATION_SEC", "60")), ge=1, le=7200)
    device: str = "/dev/video0"
    udp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    frame_stride: int = Field(default=1, ge=1, le=3600)
    requested_by: Optional[str] = Field(default="node2_motion", max_length=128)
    notes: str = Field(default="", max_length=1000)
    motion_score: Optional[float] = Field(default=None, ge=0.0)
    motion_source: str = Field(default="node2", max_length=64)
    live_mp4_fps: float = Field(default_factory=lambda: float(__import__("os").getenv("AI_CAMERA_MOTION_STREAM_LIVE_MP4_FPS", "15")), ge=1.0, le=60.0)
    live_mp4_width: int = Field(default_factory=lambda: int(__import__("os").getenv("AI_CAMERA_MOTION_STREAM_LIVE_MP4_WIDTH", "640")), ge=160, le=1920)


class DetectionPayload(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0.0, le=1.0)
    bbox_xyxy: Optional[list[float]] = Field(default=None, min_length=4, max_length=4)
    class_id: Optional[int] = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class Node2MotionEventRequest(MotionStreamRequest):
    event_type: str = Field(default="motion_detected", pattern="^motion_detected$")
    detections: list[DetectionPayload] = Field(default_factory=list, max_length=100)
    trigger_frame_id: Optional[int] = Field(default=None, ge=0)
    trigger_wall_ns: Optional[int] = Field(default=None, ge=0)
    cooldown_sec: Optional[float] = Field(default=None, ge=0.0, le=3600.0)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    camera_id: Optional[str] = None
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=1000)
