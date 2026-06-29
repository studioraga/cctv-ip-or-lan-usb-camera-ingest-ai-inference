#!/usr/bin/env python3
"""Local event/report indexing pipeline for evidence-backed future RAG.

The first production-ready slice intentionally uses deterministic local hash
embeddings so the pipeline works offline.  When qdrant-client is installed and
Qdrant is running, the same records can be upserted to Qdrant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from services.common.event_db import EventDB
from services.node1_event_indexer.qdrant_store import QdrantStore

TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")


@dataclass(frozen=True)
class EvidenceDocument:
    document_id: str
    text: str
    payload: dict[str, Any]
    vector: list[float]


def hash_embedding(text: str, *, dimension: int = 256) -> list[float]:
    if dimension <= 0:
        raise ValueError("embedding dimension must be positive")
    vec = [0.0] * dimension
    for token in TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dimension
        sign = -1.0 if digest[4] & 1 else 1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _event_text(event: dict[str, Any]) -> str:
    attrs = event.get("attrs") or {}
    detections = attrs.get("detections") or []
    parts = [
        f"event_id={event.get('event_id')}",
        f"camera_id={event.get('camera_id')}",
        f"event_type={event.get('event_type')}",
        f"ts={event.get('ts')}",
        f"label={event.get('label')}",
        f"confidence={event.get('confidence')}",
        f"caption={event.get('caption')}",
        f"session_id={attrs.get('session_id')}",
        f"motion_score={attrs.get('motion_score')}",
    ]
    for det in detections:
        parts.append(f"detected {det.get('label')} confidence={det.get('confidence')} class_id={det.get('class_id')}")
    if attrs.get("manifest_path"):
        parts.append(f"manifest_path={attrs.get('manifest_path')}")
    return " | ".join(str(p) for p in parts if p is not None)


def event_to_document(event: dict[str, Any], *, dimension: int = 256) -> EvidenceDocument:
    text = _event_text(event)
    return EvidenceDocument(
        document_id=f"event:{event.get('event_id')}",
        text=text,
        payload={
            "kind": "event",
            "event_id": event.get("event_id"),
            "camera_id": event.get("camera_id"),
            "event_type": event.get("event_type"),
            "ts": event.get("ts"),
            "session_id": (event.get("attrs") or {}).get("session_id"),
            "label": event.get("label"),
            "confidence": event.get("confidence"),
        },
        vector=hash_embedding(text, dimension=dimension),
    )


def report_to_document(path: Path, *, session_id: str, camera_id: str | None = None, dimension: int = 256) -> EvidenceDocument | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")[:20000]
    payload = {"kind": "capture_report", "session_id": session_id, "camera_id": camera_id, "path": str(path)}
    return EvidenceDocument(f"report:{session_id}", text, payload, hash_embedding(text, dimension=dimension))


def _write_jsonl(documents: Iterable[EvidenceDocument], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for doc in documents:
            f.write(json.dumps({"document_id": doc.document_id, "text": doc.text, "payload": doc.payload, "vector": doc.vector}, sort_keys=True) + "\n")
            count += 1
    return count


def build_index(
    db_path: str = "data/events/ai_camera.db",
    *,
    output_path: str = "data/index/ai_camera_evidence_index.jsonl",
    limit: int = 1000,
    dimension: int = 256,
    include_reports: bool = True,
    qdrant_url: str | None = None,
    qdrant_collection: str = "ai_camera_events",
) -> dict[str, Any]:
    db = EventDB(db_path)
    events = db.list_events(limit=limit)
    documents: list[EvidenceDocument] = [event_to_document(e, dimension=dimension) for e in events]
    if include_reports:
        for session in db.list_capture_sessions(limit=limit):
            dataset = Path(session.get("dataset_path") or "")
            doc = report_to_document(dataset / "artifacts" / "report.md", session_id=session["session_id"], camera_id=session.get("camera_id"), dimension=dimension)
            if doc is not None:
                documents.append(doc)
    out = Path(output_path)
    written = _write_jsonl(documents, out)
    qdrant = {"enabled": False}
    if qdrant_url:
        try:
            store = QdrantStore(url=qdrant_url, collection=qdrant_collection, dimension=dimension)
            store.ensure_collection()
            for doc in documents:
                store.upsert_embedding(doc.document_id, doc.vector, doc.payload | {"text": doc.text})
            qdrant = {"enabled": True, "url": qdrant_url, "collection": qdrant_collection, "upserted": len(documents)}
        except Exception as exc:  # pragma: no cover - optional external service
            qdrant = {"enabled": True, "error": str(exc), "upserted": 0}
    return {"ok": True, "db_path": db_path, "output_path": str(out), "documents": written, "dimension": dimension, "qdrant": qdrant}


def main() -> int:
    ap = argparse.ArgumentParser(description="Build local evidence index for AI Camera events and reports")
    ap.add_argument("--db-path", default="data/events/ai_camera.db")
    ap.add_argument("--output-path", default="data/index/ai_camera_evidence_index.jsonl")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--dimension", type=int, default=256)
    ap.add_argument("--no-reports", action="store_true")
    ap.add_argument("--qdrant-url", default="")
    ap.add_argument("--qdrant-collection", default="ai_camera_events")
    args = ap.parse_args()
    result = build_index(
        args.db_path,
        output_path=args.output_path,
        limit=args.limit,
        dimension=args.dimension,
        include_reports=not args.no_reports,
        qdrant_url=args.qdrant_url or None,
        qdrant_collection=args.qdrant_collection,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
