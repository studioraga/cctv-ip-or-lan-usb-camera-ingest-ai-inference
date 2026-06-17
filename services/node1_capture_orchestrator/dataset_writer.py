from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional


def _now_ns() -> int:
    return time.time_ns()


def _json_dump(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class FrameWriteResult:
    written: bool
    frame_id: int
    relative_path: str = ""
    size_bytes: int = 0
    sha256: str = ""
    write_latency_ms: float = 0.0


class DatasetWriter:
    """Write timestamped source JPEG frames and dataset artifacts for a capture session.

    The writer stores the compressed JPEG payload exactly as received from Node2's
    timestamped transport. This keeps data volume manageable compared with raw BGR
    frames while preserving source-frame bytes for later offline analysis.
    """

    def __init__(
        self,
        dataset_root: str | Path,
        session_id: str,
        *,
        camera_id: str,
        profile: str,
        transport: str,
        duration_sec: int,
        frame_stride: int = 1,
        max_bytes: Optional[int] = None,
        requested_by: Optional[str] = None,
        notes: str = "",
    ):
        if frame_stride < 1:
            raise ValueError("frame_stride must be >= 1")
        if duration_sec < 1:
            raise ValueError("duration_sec must be positive")
        self.dataset_root = Path(dataset_root)
        self.session_id = session_id
        self.session_dir = self.dataset_root / session_id
        self.frames_dir = self.session_dir / "frames"
        self.metadata_dir = self.session_dir / "metadata"
        self.artifacts_dir = self.session_dir / "artifacts"
        self.frames_jsonl = self.metadata_dir / "frames.jsonl"
        self.capture_events_jsonl = self.metadata_dir / "capture_events.jsonl"
        self.manifest_path = self.session_dir / "manifest.json"
        self.metrics_summary_path = self.artifacts_dir / "metrics_summary.json"
        self.prometheus_snapshot_path = self.artifacts_dir / "prometheus_snapshot.txt"
        self.report_path = self.artifacts_dir / "report.md"
        self.preview_path = self.artifacts_dir / "preview.mp4"
        self.camera_id = camera_id
        self.profile = profile
        self.transport = transport
        self.duration_sec = int(duration_sec)
        self.frame_stride = int(frame_stride)
        self.max_bytes = max_bytes
        self.requested_by = requested_by
        self.notes = notes
        self.created_wall_ns = _now_ns()
        self.started_wall_ns: Optional[int] = None
        self.ended_wall_ns: Optional[int] = None
        self.frames_received = 0
        self.frames_written = 0
        self.frames_skipped = 0
        self.bytes_written = 0
        self.e2e_latencies_ms: list[float] = []
        self.write_latencies_ms: list[float] = []
        self._frame_index = 0

    def prepare(self) -> None:
        self.frames_dir.mkdir(parents=True, exist_ok=False)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.started_wall_ns = _now_ns()
        self.append_event("dataset_prepared", {"dataset_path": str(self.session_dir)})

    @property
    def dataset_path(self) -> str:
        return str(self.session_dir)

    def append_event(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        record = {"ts_ns": _now_ns(), "event_type": event_type, "session_id": self.session_id}
        if data:
            record.update(data)
        with self.capture_events_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def write_frame(
        self,
        *,
        frame_id: int,
        jpeg: bytes,
        sender_wall_ns: int,
        sender_monotonic_ns: int,
        receiver_wall_ns: int,
        fragment_count: int,
        e2e_latency_ms: float,
    ) -> FrameWriteResult:
        self.frames_received += 1
        if self.frames_received % self.frame_stride != 0:
            self.frames_skipped += 1
            return FrameWriteResult(written=False, frame_id=frame_id)
        if self.max_bytes is not None and self.bytes_written + len(jpeg) > self.max_bytes:
            self.frames_skipped += 1
            return FrameWriteResult(written=False, frame_id=frame_id)

        self._frame_index += 1
        name = f"frame_{self._frame_index:06d}.jpg"
        path = self.frames_dir / name
        t0 = time.perf_counter_ns()
        path.write_bytes(jpeg)
        write_latency_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        digest = hashlib.sha256(jpeg).hexdigest()
        rel = str(path.relative_to(self.session_dir))
        size = len(jpeg)
        record = {
            "session_id": self.session_id,
            "frame_index": self._frame_index,
            "frame_id": int(frame_id),
            "sender_wall_ns": int(sender_wall_ns),
            "sender_monotonic_ns": int(sender_monotonic_ns),
            "receiver_wall_ns": int(receiver_wall_ns),
            "e2e_latency_ms": float(e2e_latency_ms),
            "fragment_count": int(fragment_count),
            "jpeg_path": rel,
            "jpeg_bytes": size,
            "sha256": digest,
            "write_latency_ms": write_latency_ms,
        }
        with self.frames_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        self.frames_written += 1
        self.bytes_written += size
        self.e2e_latencies_ms.append(float(e2e_latency_ms))
        self.write_latencies_ms.append(write_latency_ms)
        return FrameWriteResult(True, frame_id, rel, size, digest, write_latency_ms)

    @staticmethod
    def _summary(values: list[float]) -> dict[str, Optional[float]]:
        if not values:
            return {"min": None, "avg": None, "max": None, "p95": None}
        data = sorted(values)
        p95_idx = min(len(data) - 1, int(round(0.95 * (len(data) - 1))))
        return {
            "min": data[0],
            "avg": sum(data) / len(data),
            "max": data[-1],
            "p95": data[p95_idx],
        }

    def _make_preview(self) -> Optional[str]:
        """Create a lightweight MP4 preview when ffmpeg is available.

        Preview generation is best-effort and intentionally non-fatal.
        """
        if self.frames_written == 0 or shutil.which("ffmpeg") is None:
            return None
        pattern = str(self.frames_dir / "frame_%06d.jpg")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", "15", "-i", pattern,
            "-vf", "scale=640:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(self.preview_path),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=60)
            if self.preview_path.is_file():
                return str(self.preview_path.relative_to(self.session_dir))
        except Exception as exc:  # pragma: no cover - depends on host ffmpeg/codecs
            self.append_event("preview_generation_failed", {"error": str(exc)})
        return None

    def finalize(self, *, status: str, error: Optional[str] = None, prometheus_snapshot: str = "") -> dict[str, Any]:
        self.ended_wall_ns = _now_ns()
        preview_rel = self._make_preview()
        elapsed_sec = None
        if self.started_wall_ns:
            elapsed_sec = (self.ended_wall_ns - self.started_wall_ns) / 1_000_000_000.0
        metrics = {
            "session_id": self.session_id,
            "status": status,
            "frames_received": self.frames_received,
            "frames_written": self.frames_written,
            "frames_skipped": self.frames_skipped,
            "bytes_written": self.bytes_written,
            "elapsed_sec": elapsed_sec,
            "avg_fps_written": (self.frames_written / elapsed_sec) if elapsed_sec and elapsed_sec > 0 else None,
            "e2e_latency_ms": self._summary(self.e2e_latencies_ms),
            "write_latency_ms": self._summary(self.write_latencies_ms),
        }
        _json_dump(self.metrics_summary_path, metrics)
        if prometheus_snapshot:
            self.prometheus_snapshot_path.write_text(prometheus_snapshot, encoding="utf-8")

        manifest = {
            "schema_version": 1,
            "session_id": self.session_id,
            "camera_id": self.camera_id,
            "profile": self.profile,
            "transport": self.transport,
            "duration_sec": self.duration_sec,
            "frame_stride": self.frame_stride,
            "requested_by": self.requested_by,
            "notes": self.notes,
            "status": status,
            "error": error,
            "dataset_path": str(self.session_dir),
            "created_wall_ns": self.created_wall_ns,
            "started_wall_ns": self.started_wall_ns,
            "ended_wall_ns": self.ended_wall_ns,
            "frames_dir": "frames",
            "frames_jsonl": "metadata/frames.jsonl",
            "capture_events_jsonl": "metadata/capture_events.jsonl",
            "artifacts": {
                "metrics_summary": "artifacts/metrics_summary.json",
                "prometheus_snapshot": "artifacts/prometheus_snapshot.txt" if prometheus_snapshot else None,
                "report": "artifacts/report.md",
                "preview_mp4": preview_rel,
            },
            "metrics": metrics,
        }
        _json_dump(self.manifest_path, manifest)
        self.report_path.write_text(self._render_report(manifest), encoding="utf-8")
        self.append_event("dataset_finalized", {"status": status, "error": error})
        return manifest

    def _render_report(self, manifest: dict[str, Any]) -> str:
        metrics = manifest["metrics"]
        e2e = metrics["e2e_latency_ms"]
        return "\n".join([
            f"# Capture Session {self.session_id}",
            "",
            f"- Status: `{manifest['status']}`",
            f"- Camera: `{self.camera_id}`",
            f"- Profile: `{self.profile}`",
            f"- Transport: `{self.transport}`",
            f"- Requested duration: `{self.duration_sec}` sec",
            f"- Frames written: `{metrics['frames_written']}`",
            f"- Bytes written: `{metrics['bytes_written']}`",
            f"- Average written FPS: `{metrics['avg_fps_written']}`",
            f"- E2E latency avg ms: `{e2e['avg']}`",
            f"- E2E latency p95 ms: `{e2e['p95']}`",
            "",
            "## Artifacts",
            "",
            "- `manifest.json`",
            "- `metadata/frames.jsonl`",
            "- `artifacts/metrics_summary.json`",
            "- `artifacts/report.md`",
            "- `artifacts/preview.mp4` when ffmpeg preview generation succeeds",
            "",
        ])
