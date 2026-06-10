from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import FileResponse, Response

from services.common.event_db import EventDB
from services.common.policy import SecurityPolicy
from services.node1_api_gateway.schemas import StartCameraRequest, SwitchProfileRequest, QueryRequest
from services.node1_query_engine.nl_parser import parse_question

DB_PATH = os.getenv("AI_CAMERA_DB", "data/events/ai_camera.db")
POLICY_PATH = os.getenv("AI_CAMERA_POLICY", "policies/security_policy.yaml")
CAMERA_ID = os.getenv("AI_CAMERA_ID", "c922_node2_gate")
NODE2_URL = os.getenv("NODE2_URL", "http://192.168.29.188:8082")

db = EventDB(DB_PATH)
policy = SecurityPolicy(POLICY_PATH)
app = FastAPI(title="Node1 AI Camera API Gateway", version="0.1.0")

api_requests = Counter("ai_camera_api_requests_total", "API requests", ["endpoint"])
api_errors = Counter("ai_camera_api_errors_total", "API errors", ["endpoint"])

@app.on_event("startup")
def startup():
    db.upsert_camera(CAMERA_ID, "Node2 C922 Gate Camera", "usb_rtp", "192.168.29.188", "gate", True)

@app.get("/health")
def health():
    api_requests.labels("health").inc()
    return {"ok": True, "service": "node1_api_gateway", "db_path": DB_PATH}

@app.get("/cameras")
def cameras():
    api_requests.labels("cameras").inc()
    return db.list_cameras()

@app.get("/node2/status")
def node2_status(node2_url: str = NODE2_URL):
    api_requests.labels("node2_status").inc()
    try:
        return httpx.get(f"{node2_url}/stream/status", timeout=3).json()
    except Exception as exc:
        api_errors.labels("node2_status").inc()
        raise HTTPException(status_code=502, detail=str(exc))

@app.post("/cameras/{camera_id}/start")
def camera_start(camera_id: str, req: StartCameraRequest):
    api_requests.labels("camera_start").inc()
    if not policy.is_profile_allowed(camera_id, req.profile):
        raise HTTPException(status_code=403, detail=f"Profile {req.profile} is not allowed for camera {camera_id}")
    try:
        payload = {"node1_ip": req.node1_ip, "port": req.port, "profile": req.profile, "device": req.device}
        return httpx.post(f"{req.node2_url}/stream/start", json=payload, timeout=5).json()
    except Exception as exc:
        api_errors.labels("camera_start").inc()
        raise HTTPException(status_code=502, detail=str(exc))

@app.post("/cameras/{camera_id}/stop")
def camera_stop(camera_id: str, node2_url: str = NODE2_URL):
    api_requests.labels("camera_stop").inc()
    try:
        return httpx.post(f"{node2_url}/stream/stop", timeout=5).json()
    except Exception as exc:
        api_errors.labels("camera_stop").inc()
        raise HTTPException(status_code=502, detail=str(exc))

@app.post("/cameras/{camera_id}/profile")
def camera_profile(camera_id: str, req: SwitchProfileRequest):
    api_requests.labels("camera_profile").inc()
    if not policy.is_profile_allowed(camera_id, req.profile):
        raise HTTPException(status_code=403, detail=f"Profile {req.profile} is not allowed for camera {camera_id}")
    try:
        return httpx.post(f"{req.node2_url}/stream/switch-profile", json={"profile": req.profile}, timeout=5).json()
    except Exception as exc:
        api_errors.labels("camera_profile").inc()
        raise HTTPException(status_code=502, detail=str(exc))

@app.get("/events")
def events(camera_id: Optional[str] = None, event_type: Optional[str] = None, start_ts: Optional[str] = None, end_ts: Optional[str] = None, limit: int = Query(100, le=1000)):
    api_requests.labels("events").inc()
    return db.list_events(camera_id=camera_id, event_type=event_type, start_ts=start_ts, end_ts=end_ts, limit=limit)

@app.get("/events/{event_id}")
def event_detail(event_id: str):
    api_requests.labels("event_detail").inc()
    event = db.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    return event

@app.get("/clips")
def clips(camera_id: Optional[str] = None, limit: int = Query(100, le=1000)):
    api_requests.labels("clips").inc()
    return db.list_clips(camera_id=camera_id, limit=limit)

@app.get("/clips/file")
def clip_file(path: str):
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="clip file not found")
    return FileResponse(str(p))

@app.post("/query")
def query(req: QueryRequest):
    api_requests.labels("query").inc()
    intent = parse_question(req.question)
    event_type = intent.event_type
    rows = db.list_events(camera_id=req.camera_id, event_type=event_type, start_ts=req.start_ts, end_ts=req.end_ts, limit=req.limit)
    if intent.label:
        rows = [r for r in rows if (r.get("label") == intent.label or not r.get("label"))]
    if intent.summarize:
        answer = f"Found {len(rows)} matching events."
    else:
        answer = f"Found {len(rows)} matching event(s) for: {req.question}"
    return {"question": req.question, "intent": intent.__dict__, "answer": answer, "events": rows}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
