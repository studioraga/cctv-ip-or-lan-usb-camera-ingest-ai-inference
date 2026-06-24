from __future__ import annotations

import os
import time
from typing import Iterator, Optional
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest
from starlette.responses import FileResponse, HTMLResponse, Response, StreamingResponse

from services.common.event_db import EventDB, now_iso
from services.common.path_security import UnsafeMediaPath, resolve_media_path
from services.common.policy import PolicyError, SecurityPolicy
from services.node1_api_gateway.schemas import CaptureSessionRequest, MotionStreamRequest, Node2MotionEventRequest, QueryRequest, StartCameraRequest, SwitchProfileRequest
from services.node1_query_engine.nl_parser import parse_question
from services.node1_capture_orchestrator.session_manager import CaptureMetrics, CaptureSessionManager

DB_PATH = os.getenv("AI_CAMERA_DB", "data/events/ai_camera.db")
POLICY_PATH = os.getenv("AI_CAMERA_POLICY", "policies/security_policy.yaml")
CAMERA_ID = os.getenv("AI_CAMERA_ID", "c922_node2_gate")

# Startup deliberately fails when policy or migrations are invalid.
db = EventDB(DB_PATH)
policy = SecurityPolicy(POLICY_PATH)
app = FastAPI(title="Node1 AI Camera API Gateway", version="0.2.0-step1")

METRICS_REGISTRY = CollectorRegistry()
api_requests = Counter("ai_camera_api_requests_total", "API requests", ["endpoint"], registry=METRICS_REGISTRY)
api_errors = Counter("ai_camera_api_errors_total", "API errors", ["endpoint"], registry=METRICS_REGISTRY)
capture_manager = CaptureSessionManager(db, policy, metrics=CaptureMetrics(METRICS_REGISTRY))


def _requester_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _policy_denied(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)




def _motion_capture_request(req: MotionStreamRequest, *, event_label: str) -> CaptureSessionRequest:
    notes = req.notes.strip()
    trigger_note = f"{event_label}; motion_source={req.motion_source}"
    if req.motion_score is not None:
        trigger_note += f"; motion_score={req.motion_score:.3f}"
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
        response = httpx.request(method, f"{base_url}{endpoint}", timeout=5.0, **kwargs)
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


@app.on_event("startup")
def startup() -> None:
    camera = policy.camera(CAMERA_ID)
    db.upsert_camera(
        CAMERA_ID,
        "Node2 C922 Gate Camera",
        "usb_rtp",
        camera.source_ip,
        "gate",
        True,
    )


@app.get("/health")
def health():
    api_requests.labels("health").inc()
    return {"ok": True, "service": "node1_api_gateway", "db_path": DB_PATH, "policy_version": 2}


@app.get("/cameras")
def cameras():
    api_requests.labels("cameras").inc()
    return db.list_cameras()


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
        event_id = f"mot_{session['session_id']}"
        db.insert_event({
            "event_id": event_id,
            "camera_id": req.camera_id,
            "clip_id": None,
            "ts": now_iso(),
            "event_type": "motion_stream_started",
            "severity": "info",
            "label": "motion",
            "confidence": None if req.motion_score is None else min(float(req.motion_score), 1.0),
            "attrs": {"session_id": session["session_id"], "motion_source": req.motion_source, "motion_score": req.motion_score},
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
        event_id = f"mot_{session['session_id']}"
        db.insert_event({
            "event_id": event_id,
            "camera_id": req.camera_id,
            "clip_id": None,
            "ts": now_iso(),
            "event_type": "node2_motion_detected",
            "severity": "info",
            "label": "motion",
            "confidence": None if req.motion_score is None else min(float(req.motion_score), 1.0),
            "attrs": {"session_id": session["session_id"], "motion_source": req.motion_source, "motion_score": req.motion_score},
            "caption": f"Node2 reported motion and Node1 started live MP4 capture for {req.camera_id}.",
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
    active = db.get_active_capture_session(camera_id)
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
