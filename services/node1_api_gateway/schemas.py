from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, Dict, Any

class StartCameraRequest(BaseModel):
    node1_ip: str = "192.168.29.20"
    node2_url: str = "http://192.168.29.188:8082"
    port: int = 5000
    profile: str = "mjpeg_720p30"
    device: str = "/dev/video0"

class SwitchProfileRequest(BaseModel):
    node2_url: str = "http://192.168.29.188:8082"
    profile: str

class QueryRequest(BaseModel):
    question: str
    camera_id: Optional[str] = None
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    limit: int = 20
