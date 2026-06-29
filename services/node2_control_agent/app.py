from __future__ import annotations

import os
import shutil
import subprocess
from ipaddress import ip_address

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, generate_latest
from starlette.responses import JSONResponse, Response

from services.common.api_security import env_bool
from services.common.policy import PolicyError, SecurityPolicy
from services.common.request_signing import verify_signature
from .streamer_service import streamer_service

POLICY_PATH = os.getenv("AI_CAMERA_POLICY", "policies/security_policy.yaml")
policy = SecurityPolicy(POLICY_PATH)
NODE_API_SIGNING_SECRET = os.getenv("AI_CAMERA_NODE_API_SIGNING_SECRET", "").strip()
REQUIRE_SIGNED_CONTROL = env_bool("AI_CAMERA_NODE2_REQUIRE_SIGNED_CONTROL", False)
app = FastAPI(title="Node2 Camera Control Agent", version="0.3.0-production-readiness")

METRICS_REGISTRY = CollectorRegistry()
stream_running = Gauge("ai_camera_stream_running", "Whether Node2 streamer is running", ["profile"], registry=METRICS_REGISTRY)
stream_starts = Counter("ai_camera_stream_starts_total", "Node2 stream start requests", ["profile"], registry=METRICS_REGISTRY)
stream_stops = Counter("ai_camera_stream_stops_total", "Node2 stream stop requests", registry=METRICS_REGISTRY)
control_errors = Counter("ai_camera_node2_control_errors_total", "Node2 control errors", ["reason"], registry=METRICS_REGISTRY)


@app.middleware("http")
async def signed_control_middleware(request: Request, call_next):
    if REQUIRE_SIGNED_CONTROL and request.url.path not in {"/health"}:
        body = await request.body()
        request._body = body  # type: ignore[attr-defined]
        result = verify_signature(NODE_API_SIGNING_SECRET, request.method, request.url.path, request.headers, body)
        if not result.ok:
            control_errors.labels("bad_signature").inc()
            return JSONResponse(status_code=401, content={"detail": f"signed Node1 control request required: {result.reason}"})
    return await call_next(request)


class StartStreamRequest(BaseModel):
    camera_id: str = "c922_node2_gate"
    node1_ip: str = Field(default_factory=lambda: os.getenv("AI_CAMERA_NODE1_IP", ""), min_length=1)
    port: int = Field(default=5000, ge=1, le=65535)
    profile: str = "mjpeg_720p30"
    device: str = "/dev/video0"
    transport: str = Field(default="rtp", pattern="^(rtp|timed_jpeg_udp)$")


class SwitchProfileRequest(BaseModel):
    camera_id: str = "c922_node2_gate"
    profile: str


def _client_ip(request: Request) -> str:
    if request.client is None:
        raise HTTPException(status_code=403, detail="client address unavailable")
    try:
        return str(ip_address(request.client.host))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="invalid client address") from exc


def _require_trusted_client(request: Request) -> None:
    client_ip = _client_ip(request)
    try:
        trusted = policy.trusted_node1_control_ips()
    except PolicyError as exc:
        control_errors.labels("policy").inc()
        raise HTTPException(status_code=503, detail="control policy unavailable") from exc
    if client_ip not in trusted:
        control_errors.labels("untrusted_client").inc()
        raise HTTPException(status_code=403, detail="control client is not authorized")


def _validate_start(req: StartStreamRequest) -> None:
    if not policy.is_profile_allowed(req.camera_id, req.profile):
        raise HTTPException(status_code=403, detail="profile is not authorized")
    if not policy.is_stream_target_allowed(req.camera_id, req.node1_ip, req.port):
        raise HTTPException(status_code=403, detail="stream destination is not authorized")
    if not policy.is_device_allowed(req.camera_id, req.device):
        raise HTTPException(status_code=403, detail="camera device is not authorized")
    if req.transport == "timed_jpeg_udp" and req.profile.startswith("yuyv_"):
        raise HTTPException(status_code=400, detail="timed_jpeg_udp supports MJPEG profiles only")


@app.get("/health")
def health():
    return {"ok": True, "service": "node2_control_agent", "policy_version": 2}


@app.get("/camera/devices")
def camera_devices(request: Request):
    _require_trusted_client(request)
    devices = []
    if shutil.which("v4l2-ctl"):
        try:
            out = subprocess.check_output(
                ["v4l2-ctl", "--list-devices"], text=True, stderr=subprocess.STDOUT, timeout=5
            )
            return {"devices_text": out}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return {"devices_text": getattr(exc, "output", ""), "error": True}
    for i in range(8):
        path = f"/dev/video{i}"
        if os.path.exists(path):
            devices.append(path)
    return {"devices": devices}


@app.get("/stream/profiles")
def stream_profiles(request: Request):
    _require_trusted_client(request)
    return streamer_service.profiles()


@app.get("/stream/status")
def stream_status(request: Request):
    _require_trusted_client(request)
    status = streamer_service.get_status()
    if status.profile:
        stream_running.labels(status.profile).set(1 if status.running else 0)
    return status.__dict__


@app.post("/stream/start")
def stream_start(req: StartStreamRequest, request: Request):
    _require_trusted_client(request)
    _validate_start(req)
    try:
        status = streamer_service.start(req.node1_ip, req.port, req.profile, req.device, req.transport)
        stream_starts.labels(req.profile).inc()
        stream_running.labels(req.profile).set(1)
        return status.__dict__
    except Exception as exc:
        control_errors.labels("start_failure").inc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/stream/stop")
def stream_stop(request: Request):
    _require_trusted_client(request)
    try:
        old = streamer_service.get_status().profile or "unknown"
        status = streamer_service.stop()
        stream_stops.inc()
        stream_running.labels(old).set(0)
        return status.__dict__
    except Exception as exc:
        control_errors.labels("stop_failure").inc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/stream/switch-profile")
def stream_switch(req: SwitchProfileRequest, request: Request):
    _require_trusted_client(request)
    if not policy.is_profile_allowed(req.camera_id, req.profile):
        raise HTTPException(status_code=403, detail="profile is not authorized")
    try:
        status = streamer_service.switch_profile(req.profile)
        stream_starts.labels(req.profile).inc()
        stream_running.labels(req.profile).set(1)
        return status.__dict__
    except Exception as exc:
        control_errors.labels("switch_failure").inc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/metrics")
def metrics(request: Request):
    _require_trusted_client(request)
    return Response(generate_latest(METRICS_REGISTRY), media_type=CONTENT_TYPE_LATEST)
