from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StartCameraRequest(BaseModel):
    node1_ip: str = Field(default_factory=lambda: __import__("os").getenv("AI_CAMERA_NODE1_IP", ""), min_length=1)
    port: int = Field(default=5000, ge=1, le=65535)
    profile: str = "mjpeg_720p30"
    device: str = "/dev/video0"


class SwitchProfileRequest(BaseModel):
    profile: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    camera_id: Optional[str] = None
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=1000)
