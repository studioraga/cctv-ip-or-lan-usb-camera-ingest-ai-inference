from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from typing import Iterator, Optional
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse

from services.common.api_security import ApiSecurityConfig, env_bool
from services.common.event_db import EventDB, now_iso
from services.common.path_security import UnsafeMediaPath, resolve_media_path
from services.common.model_registry import ModelRegistry
from services.common.onnx_provider_validation import provider_report
from services.common.policy import PolicyError, SecurityPolicy
from services.common.request_signing import signed_headers, verify_signature
from services.common.storage_retention import StorageRetentionPolicy, storage_status
from services.node1_api_gateway.schemas import CaptureSessionRequest, MotionStreamRequest, Node2MotionEventRequest, QueryRequest, StartCameraRequest, SwitchProfileRequest
from services.node1_query_engine.nl_parser import parse_question
from services.node1_capture_orchestrator.session_manager import CaptureMetrics, CaptureSessionManager
from services.node1_event_indexer.indexer import build_index

DB_PATH = os.getenv("AI_CAMERA_DB", "data/events/ai_camera.db")
POLICY_PATH = os.getenv("AI_CAMERA_POLICY", "policies/security_policy.yaml")
CAMERA_ID = os.getenv("AI_CAMERA_CAMERA_ID", "c922_node2_gate")

# Startup deliberately fails when policy or migrations are invalid.
db = EventDB(DB_PATH)
policy = SecurityPolicy(POLICY_PATH)
api_security = ApiSecurityConfig.from_env(service="node1")
model_registry = ModelRegistry.from_env()
NODE_API_SIGNING_SECRET = os.getenv("AI_CAMERA_NODE_API_SIGNING_SECRET", "").strip()
REQUIRE_SIGNED_NODE2 = env_bool("AI_CAMERA_NODE1_REQUIRE_SIGNED_NODE2", False)


def _upsert_policy_cameras() -> None:
    for cam in policy.cameras():
        db.upsert_camera(
            cam.camera_id,
            f"AI Camera {cam.camera_id}",
            "usb_rtp",
            cam.source_ip,
            cam.camera_id,
            True,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _upsert_policy_cameras()
    yield


app = FastAPI(title="Node1 AI Camera API Gateway", version="0.3.0-production-readiness", lifespan=lifespan)

METRICS_REGISTRY = CollectorRegistry()
api_requests = Counter("ai_camera_api_requests_total", "API requests", ["endpoint"], registry=METRICS_REGISTRY)
api_errors = Counter("ai_camera_api_errors_total", "API errors", ["endpoint"], registry=METRICS_REGISTRY)
api_auth_denied = Counter("ai_camera_api_auth_denied_total", "Node1 API authorization denials", ["reason"], registry=METRICS_REGISTRY)
motion_triggers_total = Counter("ai_camera_motion_triggers_total", "Node1 accepted motion triggers by label", ["camera_id", "label"], registry=METRICS_REGISTRY)
motion_score_observed = Histogram("ai_camera_motion_score", "Node2 watcher motion score", ["camera_id"], buckets=(1, 3, 5, 8, 12, 16, 24, 32, 48, 64, float("inf")), registry=METRICS_REGISTRY)
motion_top_confidence = Gauge("ai_camera_motion_top_detection_confidence", "Top detection confidence from latest motion trigger", ["camera_id", "label"], registry=METRICS_REGISTRY)
trigger_to_capture_start_ms = Histogram("ai_camera_trigger_to_capture_start_latency_ms", "Latency from Node2 trigger wall clock to Node1 capture-session acceptance", ["camera_id"], buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")), registry=METRICS_REGISTRY)
capture_manager = CaptureSessionManager(db, policy, metrics=CaptureMetrics(METRICS_REGISTRY))


@app.middleware("http")
async def node1_security_middleware(request: Request, call_next):
    body = await request.body()
    # Keep body available for FastAPI/Pydantic after the middleware reads it.
    request._body = body  # type: ignore[attr-defined]
    client_ip = request.client.host if request.client else None
    decision = api_security.authorize(method=request.method, path=request.url.path, client_ip=client_ip, headers=request.headers)
    if not decision.allowed:
        reason = decision.reason.replace(" ", "_")[:64]
        api_auth_denied.labels(reason).inc()
        return JSONResponse(status_code=403, content={"detail": decision.reason, "required_roles": list(decision.required_roles)})
    if REQUIRE_SIGNED_NODE2 and request.url.path.startswith("/motion/events/node2"):
        sig = verify_signature(NODE_API_SIGNING_SECRET, request.method, request.url.path, request.headers, body)
        if not sig.ok:
            api_auth_denied.labels("bad_node2_signature").inc()
            return JSONResponse(status_code=401, content={"detail": f"signed Node2 request required: {sig.reason}"})
    return await call_next(request)



def _requester_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _policy_denied(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def _model_dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def _motion_event_attrs(req: MotionStreamRequest, session_id: str) -> dict:
    attrs = {
        "session_id": session_id,
        "motion_source": req.motion_source,
        "motion_score": req.motion_score,
    }
    detections = [_model_dump(d) for d in getattr(req, "detections", [])]
    if detections:
        attrs["detections"] = detections
        attrs["detection_count"] = len(detections)
        attrs["top_detection"] = detections[0]
    model_metadata = getattr(req, "model_metadata", None)
    if model_metadata:
        attrs["model_metadata"] = model_metadata
    for field in ("trigger_frame_id", "trigger_wall_ns", "cooldown_sec"):
        value = getattr(req, field, None)
        if value is not None:
            attrs[field] = value
    return attrs


def _motion_event_confidence(req: MotionStreamRequest) -> Optional[float]:
    detections = [_model_dump(d) for d in getattr(req, "detections", [])]
    if detections:
        top = max(detections, key=lambda d: float(d.get("confidence", 0.0)))
        return float(top.get("confidence", 0.0))
    return None


def _observe_motion_trigger(req: MotionStreamRequest, *, capture_start_wall_ns: Optional[int] = None) -> dict[str, Optional[float]]:
    detections = [_model_dump(d) for d in getattr(req, "detections", [])]
    top_label = "motion"
    top_conf: Optional[float] = None
    if detections:
        top = max(detections, key=lambda d: float(d.get("confidence", 0.0)))
        top_label = str(top.get("label") or "unknown")
        top_conf = float(top.get("confidence", 0.0))
        motion_top_confidence.labels(req.camera_id, top_label).set(top_conf)
    motion_triggers_total.labels(req.camera_id, top_label).inc()
    if getattr(req, "motion_score", None) is not None:
        motion_score_observed.labels(req.camera_id).observe(float(req.motion_score))
    trigger_latency: Optional[float] = None
    trigger_wall_ns = getattr(req, "trigger_wall_ns", None)
    if trigger_wall_ns is not None and capture_start_wall_ns is not None:
        trigger_latency = max(0.0, (int(capture_start_wall_ns) - int(trigger_wall_ns)) / 1_000_000.0)
        trigger_to_capture_start_ms.labels(req.camera_id).observe(trigger_latency)
    return {"top_confidence": top_conf, "trigger_to_capture_start_latency_ms": trigger_latency}


def _motion_capture_request(req: MotionStreamRequest, *, event_label: str) -> CaptureSessionRequest:
    notes = req.notes.strip()
    trigger_note = f"{event_label}; motion_source={req.motion_source}"
    if req.motion_score is not None:
        trigger_note += f"; motion_score={req.motion_score:.3f}"
    detections = [_model_dump(d) for d in getattr(req, "detections", [])]
    if detections:
        top = detections[0]
        trigger_note += f"; detections={len(detections)}; top={top.get('label')}:{float(top.get('confidence', 0.0)):.2f}"
    notes = f"{trigger_note}. {notes}".strip()
    return CaptureSessionRequest(
        camera_id=req.camera_id,
        profile=req.profile,
        duration_sec=req.duration_sec,
        device=req.device,
        transport="timed_jpeg_udp",
        udp_port=req.udp_port,
        dataset_mode="source_jpeg",
        frame_stride=req.frame_stride,
        requested_by=req.requested_by,
        notes=notes,
        live_mp4=True,
        live_mp4_fps=req.live_mp4_fps,
        live_mp4_width=req.live_mp4_width,
    )


def _stream_urls(session_id: str) -> dict[str, str]:
    return {
        "status_url": f"/capture/sessions/{session_id}",
        "artifacts_url": f"/capture/sessions/{session_id}/artifacts",
        "live_mp4_url": f"/motion/streams/{session_id}/live.mp4",
        "preview_mp4_url": f"/motion/streams/{session_id}/preview.mp4",
        "manifest_url": f"/datasets/{session_id}/manifest",
    }


def _node2_or_local_request_allowed(camera_id: str, request: Request) -> bool:
    source = _requester_ip(request)
    if source in {"127.0.0.1", "::1", os.getenv("AI_CAMERA_NODE1_IP", "")} or source is None:
        return True
    return policy.is_source_allowed(camera_id, source)


def _dataset_artifact_path(session_id: str, relative: str) -> Path:
    session = capture_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="motion stream/capture session not found")
    try:
        root = policy.media_root("dataset")
        return resolve_media_path(str(Path(session["dataset_path"]) / relative), root)
    except (PolicyError, UnsafeMediaPath, OSError) as exc:
        raise _policy_denied("motion stream artifact access denied") from exc


def _tail_growing_file(path: Path, session_id: str, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    offset = 0
    idle_after_terminal = 0
    while True:
        if path.exists() and path.is_file():
            with path.open("rb") as f:
                f.seek(offset)
                chunk = f.read(chunk_size)
            if chunk:
                offset += len(chunk)
                idle_after_terminal = 0
                yield chunk
                continue
        session = capture_manager.get_session(session_id)
        status = session.get("status") if session else "missing"
        if status not in {"pending", "running"}:
            # Give ffmpeg/file flush a brief grace period, then stop tailing.
            idle_after_terminal += 1
            if idle_after_terminal >= 8:
                break
        time.sleep(0.25)

def _node2_request(method: str, camera_id: str, endpoint: str, **kwargs):
    try:
        base_url = policy.node2_url(camera_id)
        headers = dict(kwargs.pop("headers", {}) or {})
        json_payload = kwargs.pop("json", None)
        if json_payload is not None:
            body = json.dumps(json_payload, separators=(",", ":")).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
            if NODE_API_SIGNING_SECRET:
                headers.update(signed_headers(NODE_API_SIGNING_SECRET, method, endpoint, body))
            response = httpx.request(method, f"{base_url}{endpoint}", timeout=5.0, content=body, headers=headers, **kwargs)
        else:
            if NODE_API_SIGNING_SECRET:
                headers.update(signed_headers(NODE_API_SIGNING_SECRET, method, endpoint, b""))
            response = httpx.request(method, f"{base_url}{endpoint}", timeout=5.0, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    except PolicyError as exc:
        raise _policy_denied(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        api_errors.labels(endpoint).inc()
        detail = exc.response.text[:1000]
        raise HTTPException(status_code=502, detail=f"Node2 rejected request: {detail}") from exc
    except (httpx.RequestError, ValueError) as exc:
        api_errors.labels(endpoint).inc()
        raise HTTPException(status_code=502, detail=f"Node2 communication failed: {exc}") from exc


@app.get("/health")
def health():
    api_requests.labels("health").inc()
    return {"ok": True, "service": "node1_api_gateway", "db_path": DB_PATH, "policy_version": 2}


@app.get("/cameras")
def cameras():
    api_requests.labels("cameras").inc()
    return db.list_cameras()


@app.get("/cameras/runtime")
def cameras_runtime():
    api_requests.labels("cameras_runtime").inc()
    return {
        "cameras": [
            {
                "camera_id": cam.camera_id,
                "source_ip": cam.source_ip,
                "node2_url": cam.node2_url,
                "allowed_node1_ips": list(cam.allowed_node1_ips),
                "allowed_ports": list(cam.allowed_ports),
                "allowed_profiles": list(cam.allowed_profiles),
                "allowed_devices": list(cam.allowed_devices),
            }
            for cam in policy.cameras()
        ],
        "multi_camera_ready": True,
    }


@app.get("/security/runtime")
def security_runtime():
    api_requests.labels("security_runtime").inc()
    return {
        "node1_api": api_security.security_posture(),
        "signed_node2_required": REQUIRE_SIGNED_NODE2,
        "signed_node2_secret_configured": bool(NODE_API_SIGNING_SECRET),
        "mtls_next_step": "terminate TLS/mTLS at reverse proxy or systemd socket; signed local calls are enabled in-app",
    }


@app.get("/models/registry")
def models_registry():
    api_requests.labels("models_registry").inc()
    return {"models": model_registry.list()}


@app.get("/models/verify")
def models_verify():
    api_requests.labels("models_verify").inc()
    return model_registry.verify()


@app.get("/inference/providers")
def inference_providers(requested: str = "auto"):
    api_requests.labels("inference_providers").inc()
    return provider_report(requested)


@app.get("/node2/status")
def node2_status(camera_id: str = CAMERA_ID):
    api_requests.labels("node2_status").inc()
    return _node2_request("GET", camera_id, "/stream/status")


@app.post("/cameras/{camera_id}/start")
def camera_start(camera_id: str, req: StartCameraRequest):
    api_requests.labels("camera_start").inc()
    if not policy.is_profile_allowed(camera_id, req.profile):
        raise _policy_denied(f"Profile {req.profile!r} is not allowed for camera {camera_id!r}")
    if not policy.is_stream_target_allowed(camera_id, req.node1_ip, req.port):
        raise _policy_denied(f"Stream target {req.node1_ip}:{req.port} is not allowed")
    if not policy.is_device_allowed(camera_id, req.device):
        raise _policy_denied(f"Device {req.device!r} is not allowed for camera {camera_id!r}")
    payload = {
        "camera_id": camera_id,
        "node1_ip": req.node1_ip,
        "port": req.port,
        "profile": req.profile,
        "device": req.device,
        "transport": req.transport,
    }
    return _node2_request("POST", camera_id, "/stream/start", json=payload)


@app.post("/cameras/{camera_id}/stop")
def camera_stop(camera_id: str):
    api_requests.labels("camera_stop").inc()
    # camera() makes unknown camera IDs fail closed before contacting any endpoint.
    policy.camera(camera_id)
    return _node2_request("POST", camera_id, "/stream/stop")


@app.post("/cameras/{camera_id}/profile")
def camera_profile(camera_id: str, req: SwitchProfileRequest):
    api_requests.labels("camera_profile").inc()
    if not policy.is_profile_allowed(camera_id, req.profile):
        raise _policy_denied(f"Profile {req.profile!r} is not allowed for camera {camera_id!r}")
    return _node2_request(
        "POST", camera_id, "/stream/switch-profile",
        json={"camera_id": camera_id, "profile": req.profile},
    )


@app.get("/events")
def events(camera_id: Optional[str] = None, event_type: Optional[str] = None,
           start_ts: Optional[str] = None, end_ts: Optional[str] = None,
           limit: int = Query(100, ge=1, le=1000)):
    api_requests.labels("events").inc()
    if camera_id:
        policy.camera(camera_id)
    return db.list_events(camera_id=camera_id, event_type=event_type,
                          start_ts=start_ts, end_ts=end_ts, limit=limit)


@app.get("/events/{event_id}")
def event_detail(event_id: str):
    api_requests.labels("event_detail").inc()
    event = db.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    policy.camera(event["camera_id"])
    return event


@app.get("/clips")
def clips(camera_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    api_requests.labels("clips").inc()
    if camera_id:
        policy.camera(camera_id)
    return db.list_clips(camera_id=camera_id, limit=limit)


@app.get("/clips/{clip_id}/file")
def clip_file(clip_id: str, request: Request):
    """Return a clip by opaque ID; client-provided paths are never accepted."""
    api_requests.labels("clip_file").inc()
    requester = _requester_ip(request)
    clip = db.get_clip(clip_id)
    if not clip:
        db.audit_media_access("clip", clip_id, "not_found", requester, reason="unknown clip_id")
        raise HTTPException(status_code=404, detail="clip not found")
    try:
        policy.camera(clip["camera_id"])
        path = resolve_media_path(clip["path"], policy.media_root("clip"))
    except (PolicyError, UnsafeMediaPath, OSError) as exc:
        db.audit_media_access("clip", clip_id, "denied", requester,
                              camera_id=clip.get("camera_id"), reason=str(exc))
        raise _policy_denied("clip access denied") from exc
    db.audit_media_access("clip", clip_id, "allowed", requester,
                          camera_id=clip["camera_id"], resolved_path=str(path))
    return FileResponse(path, media_type="video/mp4", filename=f"{clip_id}.mp4")


@app.get("/events/{event_id}/keyframe")
def event_keyframe(event_id: str, request: Request):
    api_requests.labels("event_keyframe").inc()
    requester = _requester_ip(request)
    record = db.get_event_keyframe(event_id)
    if not record:
        db.audit_media_access("keyframe", event_id, "not_found", requester,
                              reason="event or keyframe not found")
        raise HTTPException(status_code=404, detail="keyframe not found")
    try:
        policy.camera(record["camera_id"])
        path = resolve_media_path(record["keyframe_path"], policy.media_root("keyframe"))
    except (PolicyError, UnsafeMediaPath, OSError) as exc:
        db.audit_media_access("keyframe", event_id, "denied", requester,
                              camera_id=record.get("camera_id"), reason=str(exc))
        raise _policy_denied("keyframe access denied") from exc
    db.audit_media_access("keyframe", event_id, "allowed", requester,
                          camera_id=record["camera_id"], resolved_path=str(path))
    return FileResponse(path, media_type="image/jpeg", filename=f"{event_id}.jpg")



@app.post("/capture/sessions")
def capture_session_start(req: CaptureSessionRequest, request: Request):
    """Start a bounded Node2 capture into a Node1 source-JPEG dataset."""
    api_requests.labels("capture_session_start").inc()
    try:
        return capture_manager.start_session(req, requested_source=_requester_ip(request))
    except ValueError as exc:
        api_errors.labels("capture_session_start").inc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        api_errors.labels("capture_session_start").inc()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/capture/sessions")
def capture_sessions(camera_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    api_requests.labels("capture_sessions").inc()
    if camera_id:
        policy.camera(camera_id)
    return capture_manager.list_sessions(camera_id=camera_id, limit=limit)


@app.get("/capture/sessions/{session_id}")
def capture_session_detail(session_id: str):
    api_requests.labels("capture_session_detail").inc()
    session = capture_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="capture session not found")
    return session


@app.post("/capture/sessions/{session_id}/stop")
def capture_session_stop(session_id: str):
    api_requests.labels("capture_session_stop").inc()
    if not capture_manager.get_session(session_id):
        raise HTTPException(status_code=404, detail="capture session not found")
    return capture_manager.stop_session(session_id)


@app.get("/capture/sessions/{session_id}/artifacts")
def capture_session_artifacts(session_id: str):
    api_requests.labels("capture_session_artifacts").inc()
    if not capture_manager.get_session(session_id):
        raise HTTPException(status_code=404, detail="capture session not found")
    return db.list_capture_artifacts(session_id)


def _dataset_file(session_id: str, relative: str, media_type: str, filename: str):
    session = capture_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="capture session not found")
    try:
        root = policy.media_root("dataset")
        path = resolve_media_path(str(Path(session["dataset_path"]) / relative), root)
    except (PolicyError, UnsafeMediaPath, OSError) as exc:
        raise _policy_denied("dataset artifact access denied") from exc
    return FileResponse(path, media_type=media_type, filename=filename)


@app.get("/datasets/{session_id}/manifest")
def dataset_manifest(session_id: str):
    api_requests.labels("dataset_manifest").inc()
    return _dataset_file(session_id, "manifest.json", "application/json", f"{session_id}_manifest.json")


@app.get("/datasets/{session_id}/report")
def dataset_report(session_id: str):
    api_requests.labels("dataset_report").inc()
    return _dataset_file(session_id, "artifacts/report.md", "text/markdown", f"{session_id}_report.md")


@app.get("/ui/capture", response_class=HTMLResponse)
def capture_ui():
    api_requests.labels("capture_ui").inc()
    camera_id = CAMERA_ID
    profile = os.getenv("AI_CAMERA_PROFILE", "mjpeg_720p30")
    return f"""
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>AI Camera Capture Session</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 900px; }}
    label {{ display: block; margin-top: 1rem; font-weight: 600; }}
    input, select, textarea {{ width: 100%; padding: .5rem; font-size: 1rem; }}
    button {{ margin-top: 1rem; padding: .75rem 1.25rem; font-size: 1rem; }}
    pre {{ background: #111; color: #eee; padding: 1rem; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>AI Camera Dataset Capture</h1>
  <p>Starts a bounded Node2 timestamped JPEG capture into a Node1 dataset. Maximum duration: 7200 seconds.</p>
  <label>Camera ID</label><input id=\"camera_id\" value=\"{camera_id}\" />
  <label>Profile</label><input id=\"profile\" value=\"{profile}\" />
  <label>Duration seconds</label><input id=\"duration_sec\" type=\"number\" min=\"1\" max=\"7200\" value=\"60\" />
  <label>Frame stride</label><input id=\"frame_stride\" type=\"number\" min=\"1\" value=\"1\" />
  <label>Requested by</label><input id=\"requested_by\" value=\"grafana\" />
  <label>Notes</label><textarea id=\"notes\"></textarea>
  <button onclick=\"startCapture()\">Start Capture</button>
  <pre id=\"out\">Ready.</pre>
<script>
async function startCapture() {{
  const payload = {{
    camera_id: document.getElementById('camera_id').value,
    profile: document.getElementById('profile').value,
    duration_sec: Number(document.getElementById('duration_sec').value),
    frame_stride: Number(document.getElementById('frame_stride').value),
    requested_by: document.getElementById('requested_by').value,
    notes: document.getElementById('notes').value,
    transport: 'timed_jpeg_udp',
    dataset_mode: 'source_jpeg'
  }};
  const r = await fetch('/capture/sessions', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(payload)}});
  const data = await r.json();
  document.getElementById('out').textContent = JSON.stringify(data, null, 2);
}}
</script>
</body>
</html>
"""


@app.post("/motion/streams/start")
def motion_stream_start(req: MotionStreamRequest, request: Request):
    """Start a motion-triggered 60-second Node2->Node1 capture with live MP4 artifact generation.

    This endpoint is useful for manual validation and for a future Node2 motion
    detector to call after detecting motion locally. It reuses the Step 13
    timestamped JPEG/UDP capture path, but enables live fragmented-MP4 output.
    """
    api_requests.labels("motion_stream_start").inc()
    try:
        cap_req = _motion_capture_request(req, event_label="manual_motion_stream_start")
        session = capture_manager.start_session(cap_req, requested_source=_requester_ip(request))
        capture_start_wall_ns = time.time_ns()
        trigger_metrics = _observe_motion_trigger(req, capture_start_wall_ns=capture_start_wall_ns)
        event_id = f"mot_{session['session_id']}"
        attrs = _motion_event_attrs(req, session["session_id"])
        attrs["capture_start_wall_ns"] = capture_start_wall_ns
        attrs.update({k: v for k, v in trigger_metrics.items() if v is not None})
        db.insert_event({
            "event_id": event_id,
            "camera_id": req.camera_id,
            "clip_id": None,
            "ts": now_iso(),
            "event_type": "motion_stream_started",
            "severity": "info",
            "label": "motion",
            "confidence": _motion_event_confidence(req),
            "attrs": attrs,
            "caption": f"Motion-triggered live MP4 stream started for {req.camera_id}.",
        })
        return {**session, **_stream_urls(session["session_id"]), "event_id": event_id}
    except ValueError as exc:
        api_errors.labels("motion_stream_start").inc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        api_errors.labels("motion_stream_start").inc()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/motion/events/node2")
def node2_motion_event(req: Node2MotionEventRequest, request: Request):
    """Webhook for Node2-side motion detection to start a live MP4 stream.

    Node2 or a Node2-side detector should call this endpoint when it detects
    motion. Node1 then starts a bounded capture session and exposes a live MP4
    endpoint while recording continues.
    """
    api_requests.labels("node2_motion_event").inc()
    if not _node2_or_local_request_allowed(req.camera_id, request):
        raise _policy_denied("motion event source is not authorized")
    cap_req = _motion_capture_request(req, event_label="node2_motion_detected")
    try:
        session = capture_manager.start_session(cap_req, requested_source=_requester_ip(request))
        capture_start_wall_ns = time.time_ns()
        trigger_metrics = _observe_motion_trigger(req, capture_start_wall_ns=capture_start_wall_ns)
        event_id = f"mot_{session['session_id']}"
        attrs = _motion_event_attrs(req, session["session_id"])
        attrs["capture_start_wall_ns"] = capture_start_wall_ns
        attrs.update({k: v for k, v in trigger_metrics.items() if v is not None})
        db.insert_event({
            "event_id": event_id,
            "camera_id": req.camera_id,
            "clip_id": None,
            "ts": now_iso(),
            "event_type": "node2_motion_detected",
            "severity": "info",
            "label": "motion",
            "confidence": _motion_event_confidence(req),
            "attrs": attrs,
            "caption": f"Node2 reported motion/person/object detection and Node1 started live MP4 capture for {req.camera_id}.",
        })
        return {**session, **_stream_urls(session["session_id"]), "event_id": event_id}
    except ValueError as exc:
        api_errors.labels("node2_motion_event").inc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        api_errors.labels("node2_motion_event").inc()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/motion/streams/current")
def motion_stream_current(camera_id: str = CAMERA_ID):
    api_requests.labels("motion_stream_current").inc()
    policy.camera(camera_id)
    active = capture_manager.get_active_session(camera_id)
    if not active:
        return {"active": False, "camera_id": camera_id}
    return {"active": True, **active, **_stream_urls(active["session_id"])}


@app.get("/motion/streams/{session_id}/live.mp4")
def motion_stream_live_mp4(session_id: str):
    api_requests.labels("motion_stream_live_mp4").inc()
    session = capture_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="motion stream/capture session not found")
    path = _dataset_artifact_path(session_id, "artifacts/live.mp4")
    if not path.exists():
        if session.get("status") in {"pending", "running"}:
            return StreamingResponse(_tail_growing_file(path, session_id), media_type="video/mp4", headers={"Cache-Control": "no-store"})
        raise HTTPException(status_code=404, detail="live MP4 artifact not found for this session")
    if session.get("status") in {"pending", "running"}:
        return StreamingResponse(_tail_growing_file(path, session_id), media_type="video/mp4", headers={"Cache-Control": "no-store"})
    return FileResponse(path, media_type="video/mp4", filename=f"{session_id}_live.mp4")


@app.get("/motion/streams/{session_id}/preview.mp4")
def motion_stream_preview_mp4(session_id: str):
    api_requests.labels("motion_stream_preview_mp4").inc()
    path = _dataset_artifact_path(session_id, "artifacts/preview.mp4")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="preview MP4 is not ready")
    return FileResponse(path, media_type="video/mp4", filename=f"{session_id}_preview.mp4")


@app.get("/storage/status")
def storage_status_endpoint():
    api_requests.labels("storage_status").inc()
    return storage_status(StorageRetentionPolicy.from_env(policy.media_root("dataset")))


@app.post("/storage/prune")
def storage_prune_endpoint(dry_run: bool = True):
    api_requests.labels("storage_prune").inc()
    from services.common.storage_retention import prune_storage
    return prune_storage(StorageRetentionPolicy.from_env(policy.media_root("dataset")), dry_run=dry_run)


@app.post("/index/build")
def index_build(limit: int = Query(1000, ge=1, le=100000), output_path: str = "data/index/ai_camera_evidence_index.jsonl"):
    api_requests.labels("index_build").inc()
    return build_index(DB_PATH, output_path=output_path, limit=limit)


@app.get("/capture/sessions/{session_id}/completeness")
def capture_session_completeness(session_id: str):
    api_requests.labels("capture_session_completeness").inc()
    session = capture_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="capture session not found")
    artifacts = db.list_capture_artifacts(session_id)
    expected = {"manifest", "frames_jsonl", "metrics_summary", "report"}
    if session.get("status") == "completed":
        expected.add("preview_mp4")
    if "live_mp4" in (session.get("notes") or "") or session.get("live_mp4_ready"):
        expected.add("live_mp4")
    present = {a.get("artifact_type") for a in artifacts}
    missing = sorted(expected - present)
    return {"session_id": session_id, "complete": not missing, "expected": sorted(expected), "present": sorted(p for p in present if p), "missing": missing}


@app.post("/query")
def query(req: QueryRequest):
    api_requests.labels("query").inc()
    if req.camera_id:
        policy.camera(req.camera_id)
    intent = parse_question(req.question)
    rows = db.list_events(camera_id=req.camera_id, event_type=intent.event_type,
                          start_ts=req.start_ts, end_ts=req.end_ts, limit=req.limit)
    if intent.label:
        rows = [r for r in rows if r.get("label") == intent.label or not r.get("label")]
    answer = (f"Found {len(rows)} matching events." if intent.summarize
              else f"Found {len(rows)} matching event(s) for: {req.question}")
    return {"question": req.question, "intent": intent.__dict__, "answer": answer, "events": rows}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(METRICS_REGISTRY), media_type=CONTENT_TYPE_LATEST)
