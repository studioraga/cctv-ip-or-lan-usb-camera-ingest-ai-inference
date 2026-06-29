"""Environment-backed model registry and checksum verification."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from services.common.onnx_provider_validation import provider_report


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    role: str
    path: str
    source_url: str = ""
    sha256: str = ""
    provider: str = "auto"
    confidence_threshold: float | None = None
    iou_threshold: float | None = None
    version: str = ""
    required: bool = False

    @property
    def resolved_path(self) -> Path:
        p = Path(self.path)
        if p.is_absolute():
            return p
        repo = Path(os.getenv("AI_CAMERA_REPO_ROOT", ".")).resolve()
        return repo / p

    def verify(self) -> dict:
        path = self.resolved_path
        exists = path.is_file()
        actual = sha256_file(path) if exists else ""
        configured = bool(self.sha256)
        matches = bool(configured and actual and actual.lower() == self.sha256.lower())
        ok = exists and ((not configured and not self.required) or matches)
        return {
            **self.as_dict(include_provider=False),
            "resolved_path": str(path),
            "exists": exists,
            "sha256_configured": configured,
            "actual_sha256": actual,
            "sha256_matches": matches if configured else None,
            "required": self.required,
            "ok": ok,
            "status": "ok" if ok else ("missing_checksum" if exists and not configured else "failed"),
        }

    def as_dict(self, *, include_provider: bool = True) -> dict:
        data = {
            "model_id": self.model_id,
            "role": self.role,
            "version": self.version,
            "path": self.path,
            "source_url": self.source_url,
            "sha256": self.sha256,
            "provider": self.provider,
            "confidence_threshold": self.confidence_threshold,
            "iou_threshold": self.iou_threshold,
        }
        if include_provider:
            data["onnx_provider_report"] = provider_report(self.provider)
        return data


class ModelRegistry:
    def __init__(self, records: Iterable[ModelRecord]):
        self.records = list(records)

    @classmethod
    def from_env(cls) -> "ModelRegistry":
        require_checksum = _bool("AI_CAMERA_REQUIRE_MODEL_SHA256", False)
        yolo_path = os.getenv("AI_CAMERA_YOLO_MODEL", "models/object_detection/yolo11n.onnx")
        yolo_sha = os.getenv("AI_CAMERA_YOLO_MODEL_SHA256", "").strip()
        provider = os.getenv("AI_CAMERA_ONNX_EXECUTION_PROVIDER", "auto")
        records = [
            ModelRecord(
                model_id=os.getenv("AI_CAMERA_YOLO_MODEL_ID", "yolo11n-coco-onnx"),
                role="node1_detection_smoke_or_shared_yolo",
                version=os.getenv("AI_CAMERA_YOLO_MODEL_VERSION", ""),
                path=yolo_path,
                source_url=os.getenv("AI_CAMERA_YOLO_MODEL_URL", ""),
                sha256=yolo_sha,
                provider=provider,
                confidence_threshold=float(os.getenv("AI_CAMERA_YOLO_CONFIDENCE", "0.25")),
                iou_threshold=float(os.getenv("AI_CAMERA_YOLO_IOU", "0.45")),
                required=require_checksum,
            ),
            ModelRecord(
                model_id=os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL_ID", "node2-watcher-yolo11n-coco-onnx"),
                role="node2_motion_watcher_confirmation",
                version=os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL_VERSION", os.getenv("AI_CAMERA_YOLO_MODEL_VERSION", "")),
                path=os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL", yolo_path),
                source_url=os.getenv("AI_CAMERA_YOLO_MODEL_URL", ""),
                sha256=os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL_SHA256", yolo_sha).strip(),
                provider=os.getenv("AI_CAMERA_NODE2_WATCHER_ONNX_EXECUTION_PROVIDER", provider),
                confidence_threshold=float(os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE", "0.45")),
                iou_threshold=float(os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_IOU", "0.45")),
                required=require_checksum,
            ),
        ]
        return cls(records)

    def list(self) -> list[dict]:
        return [r.as_dict() for r in self.records]

    def verify(self) -> dict:
        results = [r.verify() for r in self.records]
        return {"ok": all(item["ok"] for item in results), "models": results}
