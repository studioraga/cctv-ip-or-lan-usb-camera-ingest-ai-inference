from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

try:
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # pragma: no cover - optional during minimal imports
    Counter = Gauge = Histogram = None

from services.common.event_db import EventDB, now_iso
from services.common.policy import SecurityPolicy
from services.common.timed_frame_protocol import TimedFrameReassembler
from services.node1_capture_orchestrator.dataset_writer import DatasetWriter


@dataclass(frozen=True)
class CaptureSessionConfig:
    session_id: str
    camera_id: str
    profile: str
    transport: str
    device: str
    node1_ip: str
    node2_ip: str
    udp_port: int
    duration_sec: int
    dataset_root: str
    frame_stride: int = 1
    max_bytes: Optional[int] = None
    requested_by: Optional[str] = None
    requested_source: Optional[str] = None
    notes: str = ""


class CaptureMetrics:
    def __init__(self, registry=None):
        self.enabled = Counter is not None
        if not self.enabled:
            return
        try:
            self.active = Gauge(
                "ai_camera_capture_session_active",
                "1 when a bounded capture session is active",
                ["camera_id", "profile", "transport"],
                registry=registry,
            )
            self.sessions_total = Counter(
                "ai_camera_capture_sessions_total",
                "Bounded capture sessions by result",
                ["camera_id", "result"],
                registry=registry,
            )
            self.elapsed_seconds = Gauge(
                "ai_camera_capture_session_elapsed_seconds",
                "Elapsed seconds for the active/latest capture session",
                ["camera_id", "profile", "transport"],
                registry=registry,
            )
            self.frames_total = Gauge(
                "ai_camera_capture_session_frames_total",
                "Frames written for the active/latest capture session",
                ["camera_id", "profile", "transport"],
                registry=registry,
            )
            self.bytes_written_total = Gauge(
                "ai_camera_capture_session_bytes_written_total",
                "Bytes written for the active/latest capture session",
                ["camera_id", "profile", "transport"],
                registry=registry,
            )
            self.dropped_frames_total = Gauge(
                "ai_camera_capture_session_dropped_frames_total",
                "Frames skipped or dropped by the capture writer",
                ["camera_id", "profile", "transport"],
                registry=registry,
            )
            self.e2e_latency_ms = Histogram(
                "ai_camera_capture_session_e2e_latency_ms",
                "Capture-session Node2 sender to Node1 receive latency in milliseconds",
                ["camera_id", "profile", "transport"],
                buckets=(1, 2.5, 5, 7.5, 10, 15, 20, 25, 33, 50, 75, 100, 150, 250, 500, float("inf")),
                registry=registry,
            )
            self.write_latency_ms = Histogram(
                "ai_camera_capture_session_write_latency_ms",
                "JPEG dataset write latency in milliseconds",
                ["camera_id", "profile", "transport"],
                buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50, 100, float("inf")),
                registry=registry,
            )
            self.disk_free_bytes = Gauge(
                "ai_camera_capture_session_disk_free_bytes",
                "Free disk bytes at the configured dataset root",
                ["path"],
                registry=registry,
            )
            self.errors_total = Counter(
                "ai_camera_capture_session_errors_total",
                "Capture-session errors by reason",
                ["camera_id", "reason"],
                registry=registry,
            )
        except ValueError:
            self.enabled = False

    def start(self, cfg: CaptureSessionConfig) -> None:
        if not self.enabled:
            return
        labels = (cfg.camera_id, cfg.profile, cfg.transport)
        self.active.labels(*labels).set(1)
        self.frames_total.labels(*labels).set(0)
        self.bytes_written_total.labels(*labels).set(0)
        self.dropped_frames_total.labels(*labels).set(0)
        self.elapsed_seconds.labels(*labels).set(0)
        self._disk_free(cfg.dataset_root)

    def observe_frame(self, cfg: CaptureSessionConfig, *, frames: int, bytes_written: int, dropped: int, e2e_ms: float, write_ms: float, elapsed_sec: float) -> None:
        if not self.enabled:
            return
        labels = (cfg.camera_id, cfg.profile, cfg.transport)
        self.frames_total.labels(*labels).set(frames)
        self.bytes_written_total.labels(*labels).set(bytes_written)
        self.dropped_frames_total.labels(*labels).set(dropped)
        self.elapsed_seconds.labels(*labels).set(elapsed_sec)
        self.e2e_latency_ms.labels(*labels).observe(e2e_ms)
        if write_ms >= 0:
            self.write_latency_ms.labels(*labels).observe(write_ms)

    def finish(self, cfg: CaptureSessionConfig, result: str) -> None:
        if not self.enabled:
            return
        labels = (cfg.camera_id, cfg.profile, cfg.transport)
        self.active.labels(*labels).set(0)
        self.sessions_total.labels(cfg.camera_id, result).inc()
        self._disk_free(cfg.dataset_root)

    def error(self, cfg: CaptureSessionConfig, reason: str) -> None:
        if self.enabled:
            self.errors_total.labels(cfg.camera_id, reason).inc()

    def _disk_free(self, dataset_root: str) -> None:
        try:
            root = Path(dataset_root)
            root.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(root)
            self.disk_free_bytes.labels(str(root)).set(usage.free)
        except Exception:
            pass


class CaptureSessionManager:
    def __init__(self, db: EventDB, policy: SecurityPolicy, *, metrics: Optional[CaptureMetrics] = None):
        self.db = db
        self.policy = policy
        self.metrics = metrics or CaptureMetrics(None)
        self.node1_ip = os.getenv("AI_CAMERA_NODE1_IP", "192.168.29.20")
        self.node2_ip = os.getenv("AI_CAMERA_NODE2_IP", "192.168.29.188")
        self.node2_api_port = int(os.getenv("AI_CAMERA_NODE2_API_PORT", "8082"))
        self.capture_udp_port = int(os.getenv("AI_CAMERA_CAPTURE_UDP_PORT", "5001"))
        self.dataset_root = os.getenv("AI_CAMERA_DATASET_ROOT", "data/datasets")
        self.max_duration_sec = int(os.getenv("AI_CAMERA_CAPTURE_MAX_DURATION_SEC", "7200"))
        self._lock = threading.Lock()
        self._stop_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}

    def start_session(self, request: Any, *, requested_source: Optional[str] = None) -> dict[str, Any]:
        duration_sec = int(request.duration_sec)
        if duration_sec < 1 or duration_sec > self.max_duration_sec:
            raise ValueError(f"duration_sec must be in 1..{self.max_duration_sec}")
        camera_id = request.camera_id
        profile = request.profile
        transport = request.transport
        device = request.device
        udp_port = int(getattr(request, "udp_port", None) or self.capture_udp_port)
        frame_stride = int(getattr(request, "frame_stride", 1) or 1)
        max_bytes = getattr(request, "max_bytes", None)

        if transport != "timed_jpeg_udp":
            raise ValueError("dataset capture currently requires transport=timed_jpeg_udp")
        if not self.policy.is_profile_allowed(camera_id, profile):
            raise ValueError(f"profile is not allowed: {profile}")
        if not self.policy.is_device_allowed(camera_id, device):
            raise ValueError(f"device is not allowed: {device}")
        if not self.policy.is_stream_target_allowed(camera_id, self.node1_ip, udp_port):
            raise ValueError(f"capture target is not allowed: {self.node1_ip}:{udp_port}")

        with self._lock:
            active = self.db.get_active_capture_session(camera_id)
            if active:
                raise RuntimeError(f"camera already has active capture session: {active['session_id']}")
            session_id = f"cap_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            cfg = CaptureSessionConfig(
                session_id=session_id,
                camera_id=camera_id,
                profile=profile,
                transport=transport,
                device=device,
                node1_ip=self.node1_ip,
                node2_ip=self.node2_ip,
                udp_port=udp_port,
                duration_sec=duration_sec,
                dataset_root=self.dataset_root,
                frame_stride=frame_stride,
                max_bytes=max_bytes,
                requested_by=getattr(request, "requested_by", None),
                requested_source=requested_source,
                notes=getattr(request, "notes", ""),
            )
            dataset_path = str(Path(self.dataset_root) / session_id)
            self.db.create_capture_session({
                "session_id": session_id,
                "camera_id": camera_id,
                "requested_by": cfg.requested_by,
                "requested_source": requested_source,
                "profile": profile,
                "transport": transport,
                "device": device,
                "node1_ip": self.node1_ip,
                "node2_ip": self.node2_ip,
                "udp_port": udp_port,
                "duration_sec": duration_sec,
                "status": "pending",
                "dataset_path": dataset_path,
                "notes": cfg.notes,
                "frame_stride": frame_stride,
                "max_bytes": max_bytes,
            })
            stop_event = threading.Event()
            thread = threading.Thread(target=self._run_session, args=(cfg, stop_event), name=f"capture-{session_id}", daemon=True)
            self._stop_events[session_id] = stop_event
            self._threads[session_id] = thread
            thread.start()
            return self.get_session(session_id) or {"session_id": session_id, "status": "pending"}

    def stop_session(self, session_id: str) -> dict[str, Any]:
        event = self._stop_events.get(session_id)
        if event:
            event.set()
        try:
            self._node2_stop()
        except Exception:
            pass
        return self.get_session(session_id) or {"session_id": session_id, "status": "unknown"}

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        return self.db.get_capture_session(session_id)

    def list_sessions(self, *, camera_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.list_capture_sessions(camera_id=camera_id, limit=limit)

    def _node2_url(self) -> str:
        return f"http://{self.node2_ip}:{self.node2_api_port}"

    def _node2_start(self, cfg: CaptureSessionConfig) -> None:
        payload = {
            "camera_id": cfg.camera_id,
            "node1_ip": cfg.node1_ip,
            "port": cfg.udp_port,
            "profile": cfg.profile,
            "device": cfg.device,
            "transport": cfg.transport,
        }
        resp = httpx.post(f"{self._node2_url()}/stream/start", json=payload, timeout=10.0)
        resp.raise_for_status()

    def _node2_stop(self) -> None:
        resp = httpx.post(f"{self._node2_url()}/stream/stop", timeout=10.0)
        resp.raise_for_status()

    def _run_session(self, cfg: CaptureSessionConfig, stop_event: threading.Event) -> None:
        writer = DatasetWriter(
            cfg.dataset_root,
            cfg.session_id,
            camera_id=cfg.camera_id,
            profile=cfg.profile,
            transport=cfg.transport,
            duration_sec=cfg.duration_sec,
            frame_stride=cfg.frame_stride,
            max_bytes=cfg.max_bytes,
            requested_by=cfg.requested_by,
            notes=cfg.notes,
        )
        status = "completed"
        error: Optional[str] = None
        sock: Optional[socket.socket] = None
        started = time.monotonic()
        try:
            writer.prepare()
            self.db.update_capture_session(cfg.session_id, status="running", started_at=now_iso(), dataset_path=writer.dataset_path)
            self.metrics.start(cfg)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", cfg.udp_port))
            sock.settimeout(0.5)
            self._node2_start(cfg)
            writer.append_event("node2_stream_started", {"target": f"{cfg.node1_ip}:{cfg.udp_port}"})
            reassembler = TimedFrameReassembler(max_inflight_frames=128)
            deadline = time.monotonic() + cfg.duration_sec
            while not stop_event.is_set() and time.monotonic() < deadline:
                try:
                    data, _addr = sock.recvfrom(65536)
                except socket.timeout:
                    continue
                frame = reassembler.push(data)
                if frame is None:
                    continue
                receiver_wall_ns = time.time_ns()
                e2e_ms = max(0.0, (receiver_wall_ns - frame.sender_wall_ns) / 1_000_000.0)
                result = writer.write_frame(
                    frame_id=frame.frame_id,
                    jpeg=frame.jpeg,
                    sender_wall_ns=frame.sender_wall_ns,
                    sender_monotonic_ns=frame.sender_monotonic_ns,
                    receiver_wall_ns=receiver_wall_ns,
                    fragment_count=frame.fragment_count,
                    e2e_latency_ms=e2e_ms,
                )
                elapsed = max(0.0, time.monotonic() - started)
                if result.written:
                    self.metrics.observe_frame(
                        cfg,
                        frames=writer.frames_written,
                        bytes_written=writer.bytes_written,
                        dropped=writer.frames_skipped,
                        e2e_ms=e2e_ms,
                        write_ms=result.write_latency_ms,
                        elapsed_sec=elapsed,
                    )
                if writer.max_bytes is not None and writer.bytes_written >= writer.max_bytes:
                    writer.append_event("max_bytes_reached", {"bytes_written": writer.bytes_written})
                    break
            if stop_event.is_set():
                status = "cancelled"
        except Exception as exc:
            status = "failed"
            error = str(exc)
            self.metrics.error(cfg, type(exc).__name__)
            try:
                writer.append_event("capture_failed", {"error": error})
            except Exception:
                pass
        finally:
            try:
                self._node2_stop()
            except Exception as exc:
                if status == "completed":
                    writer.append_event("node2_stop_warning", {"error": str(exc)})
            if sock is not None:
                sock.close()
            manifest = writer.finalize(status=status, error=error)
            self.db.update_capture_session(
                cfg.session_id,
                status=status,
                ended_at=now_iso(),
                error=error,
                manifest_path=str(writer.manifest_path),
                frames_written=writer.frames_written,
                bytes_written=writer.bytes_written,
                dropped_frames=writer.frames_skipped,
                updated_at=now_iso(),
            )
            artifacts = [
                ("manifest", writer.manifest_path, "application/json"),
                ("frames_jsonl", writer.frames_jsonl, "application/x-ndjson"),
                ("metrics_summary", writer.metrics_summary_path, "application/json"),
                ("report", writer.report_path, "text/markdown"),
            ]
            if writer.preview_path.is_file():
                artifacts.append(("preview_mp4", writer.preview_path, "video/mp4"))
            for artifact_type, path, media_type in artifacts:
                self.db.insert_capture_artifact({
                    "artifact_id": f"{cfg.session_id}_{artifact_type}",
                    "session_id": cfg.session_id,
                    "artifact_type": artifact_type,
                    "path": str(path),
                    "media_type": media_type,
                    "size_bytes": path.stat().st_size if path.exists() else None,
                    "sha256": _sha256_file(path) if path.exists() and path.is_file() else None,
                })
            self.metrics.finish(cfg, status)
            self._stop_events.pop(cfg.session_id, None)
            self._threads.pop(cfg.session_id, None)


def _sha256_file(path: Path) -> str:
    h = __import__("hashlib").sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
