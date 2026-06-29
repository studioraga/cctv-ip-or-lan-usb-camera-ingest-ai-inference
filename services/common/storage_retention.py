"""Storage quota and retention helpers for customer-prem dataset artifacts."""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class StorageRetentionPolicy:
    root: Path
    max_bytes: int = 0
    min_free_bytes: int = 0
    retention_days: int = 0
    prune_batch: int = 50

    @classmethod
    def from_env(cls, root: str | Path | None = None) -> "StorageRetentionPolicy":
        return cls(
            root=Path(root or os.getenv("AI_CAMERA_DATASET_ROOT", "data/datasets")),
            max_bytes=_int_env("AI_CAMERA_STORAGE_MAX_BYTES", 0),
            min_free_bytes=_int_env("AI_CAMERA_STORAGE_MIN_FREE_BYTES", 0),
            retention_days=_int_env("AI_CAMERA_STORAGE_RETENTION_DAYS", 0),
            prune_batch=_int_env("AI_CAMERA_STORAGE_PRUNE_BATCH", 50),
        )


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _session_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.iterdir() if p.is_dir()]


def storage_status(policy: StorageRetentionPolicy) -> dict:
    root = policy.root
    root.mkdir(parents=True, exist_ok=True)
    sessions = []
    total = 0
    for p in _session_dirs(root):
        size = _dir_size(p)
        total += size
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0.0
        sessions.append({"path": str(p), "session_id": p.name, "size_bytes": size, "mtime": mtime})
    usage = shutil.disk_usage(root)
    return {
        "root": str(root),
        "session_count": len(sessions),
        "dataset_bytes": total,
        "disk_free_bytes": usage.free,
        "disk_total_bytes": usage.total,
        "policy": {
            "max_bytes": policy.max_bytes,
            "min_free_bytes": policy.min_free_bytes,
            "retention_days": policy.retention_days,
            "prune_batch": policy.prune_batch,
        },
        "sessions": sorted(sessions, key=lambda item: item["mtime"]),
    }


def prune_storage(policy: StorageRetentionPolicy, *, dry_run: bool = True) -> dict:
    status = storage_status(policy)
    now = time.time()
    cutoff = now - policy.retention_days * 86400 if policy.retention_days > 0 else None
    candidates = []
    for item in status["sessions"]:
        over_age = cutoff is not None and item["mtime"] < cutoff
        over_quota = policy.max_bytes > 0 and status["dataset_bytes"] > policy.max_bytes
        low_space = policy.min_free_bytes > 0 and status["disk_free_bytes"] < policy.min_free_bytes
        if over_age or over_quota or low_space:
            candidates.append({**item, "reason": "retention_or_quota"})
    deleted = []
    bytes_deleted = 0
    for item in candidates[: max(0, policy.prune_batch)]:
        path = Path(item["path"])
        bytes_deleted += int(item["size_bytes"])
        deleted.append(item)
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
    return {
        "dry_run": dry_run,
        "root": str(policy.root),
        "candidates": candidates,
        "deleted": deleted,
        "bytes_selected": bytes_deleted,
        "before": {k: v for k, v in status.items() if k != "sessions"},
    }
