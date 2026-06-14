from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest
from starlette.responses import FileResponse, Response

from services.common.event_db import EventDB
from services.common.path_security import UnsafeMediaPath, resolve_media_path
from services.common.policy import PolicyError, SecurityPolicy
from services.node1_api_gateway.schemas import QueryRequest, StartCameraRequest, SwitchProfileRequest
from services.node1_query_engine.nl_parser import parse_question

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


def _requester_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _policy_denied(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


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
