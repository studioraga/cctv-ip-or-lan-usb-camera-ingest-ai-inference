from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .streamer_service import streamer_service

app = FastAPI(title="Node2 Camera Control Agent", version="0.1.0")

stream_running = Gauge("ai_camera_stream_running", "Whether Node2 streamer is running", ["profile"])
stream_starts = Counter("ai_camera_stream_starts_total", "Node2 stream start requests", ["profile"])
stream_stops = Counter("ai_camera_stream_stops_total", "Node2 stream stop requests")
control_errors = Counter("ai_camera_node2_control_errors_total", "Node2 control errors")


class StartStreamRequest(BaseModel):
    node1_ip: str = "192.168.29.20"
    port: int = 5000
    profile: str = "mjpeg_720p30"
    device: str = "/dev/video0"


class SwitchProfileRequest(BaseModel):
    profile: str


@app.get("/health")
def health():
    return {"ok": True, "service": "node2_control_agent"}


@app.get("/camera/devices")
def camera_devices():
    devices = []
    if shutil.which("v4l2-ctl"):
        try:
            out = subprocess.check_output(["v4l2-ctl", "--list-devices"], text=True, stderr=subprocess.STDOUT)
            return {"devices_text": out}
        except subprocess.CalledProcessError as exc:
            return {"devices_text": exc.output, "error": True}
    for i in range(8):
        p = f"/dev/video{i}"
        if os.path.exists(p):
            devices.append(p)
    return {"devices": devices}


@app.get("/stream/profiles")
def stream_profiles():
    return streamer_service.profiles()


@app.get("/stream/status")
def stream_status():
    st = streamer_service.get_status()
    if st.profile:
        stream_running.labels(st.profile).set(1 if st.running else 0)
    return st.__dict__


@app.post("/stream/start")
def stream_start(req: StartStreamRequest):
    try:
        st = streamer_service.start(req.node1_ip, req.port, req.profile, req.device)
        stream_starts.labels(req.profile).inc()
        stream_running.labels(req.profile).set(1)
        return st.__dict__
    except Exception as exc:
        control_errors.inc()
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/stream/stop")
def stream_stop():
    try:
        old = streamer_service.get_status().profile or "unknown"
        st = streamer_service.stop()
        stream_stops.inc()
        stream_running.labels(old).set(0)
        return st.__dict__
    except Exception as exc:
        control_errors.inc()
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/stream/switch-profile")
def stream_switch(req: SwitchProfileRequest):
    try:
        st = streamer_service.switch_profile(req.profile)
        stream_starts.labels(req.profile).inc()
        stream_running.labels(req.profile).set(1)
        return st.__dict__
    except Exception as exc:
        control_errors.inc()
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
