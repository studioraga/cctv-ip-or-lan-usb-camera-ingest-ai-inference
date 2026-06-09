#!/usr/bin/env python3
"""Node1 RTP camera receiver agent.

Receives RTP camera streams from Node2 or compatible RTP senders over UDP.

Features:
  - MJPEG RTP receiver profiles: 480p30, 720p30, 720p60, 1080p30
  - Raw RTP YUYV debug receiver profile: 640x480@30
  - OpenCV display and FPS overlay
  - JSONL telemetry/event log
  - Optional Prometheus metrics endpoint
  - Optional ONNX Runtime model hook
  - Optional SQLite event persistence
  - Optional lightweight motion event trigger with keyframe/clip capture
  - Signal-safe shutdown and no-frame watchdog for long-running service use

The default behavior remains compatible with the original working lab:
  python agents/node1/node1_receiver_agent.py --profile mjpeg_720p30 --port 5000
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import threading
import queue
import sys
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np

try:
    import onnxruntime as ort
except ImportError:  # optional dependency in some bring-up tests
    ort = None

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
except ImportError:  # optional until metrics are installed
    Counter = Gauge = Histogram = None
    start_http_server = None

RUNNING = True


def handle_signal(signum, frame):
    """Request graceful shutdown from SIGINT/SIGTERM."""
    global RUNNING
    print(f"\n[INFO] Signal received: {signum}; shutting down receiver loop...", flush=True)
    RUNNING = False


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


PROFILES: Dict[str, Dict[str, Any]] = {
    "mjpeg_480p30": {
        "encoding": "JPEG", "width": 640, "height": 480, "fps": 30,
        "payload": 26, "format": "BGR", "description": "RTP/JPEG MJPEG 640x480@30",
    },
    "mjpeg_720p30": {
        "encoding": "JPEG", "width": 1280, "height": 720, "fps": 30,
        "payload": 26, "format": "BGR", "description": "RTP/JPEG MJPEG 1280x720@30",
    },
    "mjpeg_720p60": {
        "encoding": "JPEG", "width": 1280, "height": 720, "fps": 60,
        "payload": 26, "format": "BGR", "description": "RTP/JPEG MJPEG 1280x720@60",
    },
    "mjpeg_1080p30": {
        "encoding": "JPEG", "width": 1920, "height": 1080, "fps": 30,
        "payload": 26, "format": "BGR", "description": "RTP/JPEG MJPEG 1920x1080@30",
    },
    "yuyv_640x480": {
        "encoding": "RAW", "width": 640, "height": 480, "fps": 30,
        "payload": 96, "raw_format": "YUY2", "format": "BGR",
        "description": "RTP/raw YUYV 640x480@30, sent as UYVY via rtpvrawpay",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_mjpeg_pipeline(
    port: int,
    payload: int,
    buffer_size: int,
    use_jitterbuffer: bool,
    jitter_latency_ms: int,
) -> str:
    jitter = (
        f"rtpjitterbuffer latency={jitter_latency_ms} drop-on-latency=true ! "
        if use_jitterbuffer else ""
    )
    return (
        f'udpsrc port={port} buffer-size={buffer_size} '
        f'caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload={payload}" ! '
        f'{jitter}'
        'queue leaky=downstream max-size-buffers=4 ! '
        'rtpjpegdepay ! jpegdec ! videoconvert ! video/x-raw,format=BGR ! '
        # wait-on-eos=false avoids appsink waiting during EOS/shutdown.
        'appsink name=appsink0 drop=true sync=false max-buffers=1 wait-on-eos=false emit-signals=false'
    )


def build_yuyv_pipeline(
    port: int,
    payload: int,
    width: int,
    height: int,
    fps: int,
    buffer_size: int,
    use_jitterbuffer: bool,
    jitter_latency_ms: int,
) -> str:
    jitter = (
        f"rtpjitterbuffer latency={jitter_latency_ms} drop-on-latency=true ! "
        if use_jitterbuffer else ""
    )
    return (
        f'udpsrc port={port} buffer-size={buffer_size} '
        f'caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=RAW,payload={payload},'
        f'sampling=YCbCr-4:2:2,depth=(string)8,width=(string){width},height=(string){height},'
        f'colorimetry=(string)BT601-5,a-framerate=(string){fps}.000000" ! '
        f'{jitter}'
        'queue leaky=downstream max-size-buffers=4 ! rtpvrawdepay ! videoconvert ! '
        'video/x-raw,format=BGR ! '
        'appsink name=appsink0 drop=true sync=false max-buffers=1 wait-on-eos=false emit-signals=false'
    )


def build_pipeline(
    profile_name: str,
    port: int,
    buffer_size: int,
    use_jitterbuffer: bool,
    jitter_latency_ms: int,
) -> str:
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown profile: {profile_name}")
    p = PROFILES[profile_name]
    if p["encoding"] == "JPEG":
        return build_mjpeg_pipeline(port, p["payload"], buffer_size, use_jitterbuffer, jitter_latency_ms)
    if p["encoding"] == "RAW":
        return build_yuyv_pipeline(
            port, p["payload"], p["width"], p["height"], p["fps"],
            buffer_size, use_jitterbuffer, jitter_latency_ms,
        )
    raise ValueError(f"Unsupported encoding: {p['encoding']}")


def ensure_parent(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def write_jsonl(event_log: Optional[str], event: Dict[str, Any]) -> None:
    if not event_log:
        return
    ensure_parent(event_log)
    with open(event_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


class EventStore:
    """Small SQLite event store used by the receiver and API gateway."""

    def __init__(self, db_path: Optional[str]):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        if db_path:
            ensure_parent(db_path)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.init_schema()

    def init_schema(self) -> None:
        assert self.conn is not None
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cameras (
                camera_id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                source TEXT,
                location TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clips (
                clip_id TEXT PRIMARY KEY,
                camera_id TEXT NOT NULL,
                start_ts TEXT NOT NULL,
                end_ts TEXT NOT NULL,
                path TEXT NOT NULL,
                keyframe_path TEXT,
                duration_sec REAL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                camera_id TEXT NOT NULL,
                clip_id TEXT,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                label TEXT,
                confidence REAL,
                track_id TEXT,
                zone_id TEXT,
                bbox_json TEXT,
                attrs_json TEXT,
                caption TEXT,
                embedding_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_camera_ts ON events(camera_id, ts);
            CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts);
            CREATE INDEX IF NOT EXISTS idx_events_zone_ts ON events(zone_id, ts);
            """
        )
        self.conn.commit()

    def insert_event(self, event: Dict[str, Any]) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            """
            INSERT OR REPLACE INTO events (
                event_id, camera_id, clip_id, ts, event_type, severity, label,
                confidence, track_id, zone_id, bbox_json, attrs_json, caption,
                embedding_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"], event["camera_id"], event.get("clip_id"), event["ts"],
                event["event_type"], event.get("severity", "info"), event.get("label"),
                event.get("confidence"), event.get("track_id"), event.get("zone_id"),
                json.dumps(event.get("bbox")) if event.get("bbox") is not None else None,
                json.dumps(event.get("attrs", {})), event.get("caption"),
                event.get("embedding_id"), now_iso(),
            ),
        )
        self.conn.commit()

    def insert_clip(self, clip: Dict[str, Any]) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            """
            INSERT OR REPLACE INTO clips (
                clip_id, camera_id, start_ts, end_ts, path, keyframe_path, duration_sec, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clip["clip_id"], clip["camera_id"], clip["start_ts"], clip["end_ts"],
                clip["path"], clip.get("keyframe_path"), clip.get("duration_sec"), now_iso(),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None


class Metrics:
    def __init__(self, enabled: bool, port: int):
        self.enabled = enabled and start_http_server is not None
        self.receiver_fps = None
        self.frames_total = None
        self.decode_failures = None
        self.inference_latency = None
        self.events_total = None
        self.last_frame_age = None
        if self.enabled:
            try:
                self.receiver_fps = Gauge("ai_camera_receiver_fps", "Receiver FPS", ["camera_id", "profile"])
                self.frames_total = Counter("ai_camera_frames_total", "Frames received", ["camera_id", "profile"])
                self.decode_failures = Counter("ai_camera_decode_failures_total", "Frame read/decode failures", ["camera_id", "profile"])
                self.inference_latency = Histogram("ai_camera_inference_latency_ms", "Inference latency in milliseconds", ["camera_id", "model"])
                self.events_total = Counter("ai_camera_events_total", "AI camera events", ["camera_id", "event_type"])
                self.last_frame_age = Gauge("ai_camera_receiver_last_frame_age_seconds", "Seconds since last received frame", ["camera_id", "profile"])
                start_http_server(port)
                print(f"[INFO] Prometheus metrics listening on :{port}/metrics")
            except ValueError as exc:
                # Handles duplicate metric registration if code is imported/reloaded in tests.
                self.enabled = False
                print(f"[WARN] Could not register Prometheus metrics: {exc}; metrics disabled")
            except OSError as exc:
                # Handles port already in use.
                self.enabled = False
                print(f"[WARN] Could not start Prometheus server on port {port}: {exc}; metrics disabled")
        elif enabled:
            print("[WARN] prometheus_client is not installed; metrics disabled")

    def set_fps(self, camera_id: str, profile: str, fps: float):
        if self.receiver_fps:
            self.receiver_fps.labels(camera_id, profile).set(fps)

    def inc_frame(self, camera_id: str, profile: str):
        if self.frames_total:
            self.frames_total.labels(camera_id, profile).inc()

    def inc_decode_fail(self, camera_id: str, profile: str):
        if self.decode_failures:
            self.decode_failures.labels(camera_id, profile).inc()

    def observe_infer(self, camera_id: str, model: str, infer_ms: float):
        if self.inference_latency:
            self.inference_latency.labels(camera_id, model).observe(infer_ms)

    def inc_event(self, camera_id: str, event_type: str):
        if self.events_total:
            self.events_total.labels(camera_id, event_type).inc()

    def set_last_frame_age(self, camera_id: str, profile: str, age_sec: float):
        if self.last_frame_age:
            self.last_frame_age.labels(camera_id, profile).set(age_sec)


class OptionalOnnxModel:
    def __init__(self, model_path: Optional[str]):
        self.model_path = model_path
        self.session = None
        self.input_name = None
        if not model_path:
            return
        if ort is None:
            raise RuntimeError("onnxruntime is not installed, but --model was provided")
        if not os.path.exists(model_path):
            raise FileNotFoundError(model_path)
        providers = ort.get_available_providers()
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        print(f"[INFO] Loaded ONNX model: {model_path}")
        print(f"[INFO] ONNX providers: {providers}")

    def infer(self, frame: np.ndarray) -> Optional[float]:
        if self.session is None:
            return None
        t0 = time.time()
        resized = cv2.resize(frame, (224, 224))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = rgb.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))
        tensor = np.expand_dims(tensor, axis=0)
        _ = self.session.run(None, {self.input_name: tensor})
        return (time.time() - t0) * 1000.0


class MotionTrigger:
    """Lightweight motion detector for first event/clip capture validation."""

    def __init__(self, enabled: bool, threshold: float, cooldown_sec: float):
        self.enabled = enabled
        self.threshold = threshold
        self.cooldown_sec = cooldown_sec
        self.prev_gray = None
        self.last_event_ts = 0.0

    def detect(self, frame: np.ndarray) -> tuple[bool, float]:
        if not self.enabled:
            return False, 0.0
        small = cv2.resize(frame, (320, 180))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if self.prev_gray is None:
            self.prev_gray = gray
            return False, 0.0
        diff = cv2.absdiff(self.prev_gray, gray)
        self.prev_gray = gray
        score = float(np.mean(diff))
        now = time.time()
        if score >= self.threshold and now - self.last_event_ts >= self.cooldown_sec:
            self.last_event_ts = now
            return True, score
        return False, score


def save_keyframe(frame: np.ndarray, keyframe_dir: str, event_id: str) -> str:
    Path(keyframe_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(keyframe_dir) / f"{event_id}.jpg")
    if not cv2.imwrite(path, frame):
        raise RuntimeError(f"Failed to write keyframe: {path}")
    return path


def save_clip(frames: list[np.ndarray], clip_dir: str, camera_id: str, fps: float, event_id: str) -> Optional[str]:
    if not frames:
        return None
    out_dir = Path(clip_dir) / camera_id / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = str(out_dir / f"{event_id}.mp4")
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), max(float(fps), 1.0), (w, h))
    if not writer.isOpened():
        print(f"[WARN] Could not open VideoWriter for {path}")
        return None
    try:
        for f in frames:
            writer.write(f)
    finally:
        writer.release()
    return path


def draw_overlay(frame: np.ndarray, profile_name: str, fps: float, infer_ms: Optional[float]) -> np.ndarray:
    overlay = frame.copy()
    cv2.putText(overlay, f"Node1 Receiver | {profile_name} | FPS={fps:.2f}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(overlay, "infer_ms=None" if infer_ms is None else f"infer_ms={infer_ms:.2f}", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
    return overlay



class CaptureWorker:
    """Read OpenCV frames in a daemon thread so the main loop can enforce timeouts.

    OpenCV's GStreamer VideoCapture.read() can block when a UDP/RTP sender stops.
    Running read() in a daemon thread allows the main control loop to observe timeouts,
    release resources, and exit instead of hanging forever inside cap.read().
    """

    def __init__(self, cap: cv2.VideoCapture, max_queue: int = 2):
        self.cap = cap
        self.frames: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=max_queue)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="capture-worker", daemon=True)
        self.read_failures = 0
        self.last_error: Optional[str] = None

    def start(self) -> None:
        self.thread.start()

    def _put_latest(self, frame: np.ndarray) -> None:
        # Keep only the latest frame to preserve realtime behavior.
        if self.frames.full():
            try:
                self.frames.get_nowait()
            except queue.Empty:
                pass
        try:
            self.frames.put_nowait(frame)
        except queue.Full:
            pass

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                ok, frame = self.cap.read()
            except Exception as exc:  # defensive; OpenCV usually returns False instead
                self.read_failures += 1
                self.last_error = str(exc)
                time.sleep(0.05)
                continue

            if not ok or frame is None:
                self.read_failures += 1
                time.sleep(0.05)
                continue

            self._put_latest(frame)

    def read_latest(self, timeout: float = 0.2) -> Optional[np.ndarray]:
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        self.stop_event.set()

    def join(self, timeout: float = 1.0) -> None:
        if self.thread.is_alive():
            self.thread.join(timeout=timeout)

def main() -> int:
    parser = argparse.ArgumentParser(description="Node1 RTP camera receiver agent")
    parser.add_argument("--profile", default="mjpeg_720p30", choices=sorted(PROFILES.keys()), help="Receiver profile. Must match sender profile.")
    parser.add_argument("--camera-id", default="c922_node2_gate")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--buffer-size", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--display", action="store_true")
    parser.add_argument("--event-log", default="results/node1/events.jsonl")
    parser.add_argument("--db-path", default=None, help="Optional SQLite DB path, e.g. data/events/ai_camera.db")
    parser.add_argument("--model", default=None, help="Optional generic ONNX model path")
    parser.add_argument("--report-interval", type=float, default=2.0)
    parser.add_argument("--jitterbuffer", action="store_true")
    parser.add_argument("--jitter-latency-ms", type=int, default=50)
    parser.add_argument("--window-name", default="Node2 C922 stream on Node1")
    parser.add_argument("--metrics", action="store_true", help="Expose Prometheus metrics")
    parser.add_argument("--metrics-port", type=int, default=9101)
    parser.add_argument("--motion-events", action="store_true", help="Enable simple motion events for validating event DB/keyframes/clips")
    parser.add_argument("--motion-threshold", type=float, default=12.0)
    parser.add_argument("--motion-cooldown-sec", type=float, default=10.0)
    parser.add_argument("--clip-dir", default="data/clips")
    parser.add_argument("--keyframe-dir", default="data/keyframes")
    parser.add_argument("--pre-event-sec", type=float, default=3.0)
    parser.add_argument("--no-frame-timeout-sec", type=float, default=10.0, help="Exit if no frames are received for this many seconds after at least one frame has arrived")
    parser.add_argument("--startup-timeout-sec", type=float, default=30.0, help="Exit if the first frame does not arrive within this many seconds")
    parser.add_argument("--exit-on-no-frames", action=argparse.BooleanOptionalAction, default=True, help="Exit instead of looping forever when the stream disappears")
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    pipeline = build_pipeline(args.profile, args.port, args.buffer_size, args.jitterbuffer, args.jitter_latency_ms)
    print(f"[INFO] Profile: {args.profile}")
    print(f"[INFO] Description: {profile['description']}")
    print("[INFO] Opening pipeline:")
    print(pipeline)

    metrics = Metrics(args.metrics, args.metrics_port)
    event_store = EventStore(args.db_path)
    model = OptionalOnnxModel(args.model)
    motion = MotionTrigger(args.motion_events, args.motion_threshold, args.motion_cooldown_sec)
    frame_buffer = deque(maxlen=max(1, int(args.pre_event_sec * float(profile["fps"]))))

    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print("[ERROR] Failed to open GStreamer pipeline", file=sys.stderr)
        event_store.close()
        return 1

    capture = CaptureWorker(cap, max_queue=2)
    capture.start()

    frames_total = 0
    frames_interval = 0
    consecutive_read_failures = 0
    t_start = time.time()
    t_last_report = t_start
    last_frame_ts: Optional[float] = None

    write_jsonl(
        args.event_log,
        {
            "ts": time.time(), "iso_ts": now_iso(), "event": "receiver_started",
            "camera_id": args.camera_id, "profile": args.profile, "port": args.port,
            "pipeline": pipeline,
        },
    )

    exit_code = 0

    try:
        while RUNNING:
            frame = capture.read_latest(timeout=0.2)
            now = time.time()

            if last_frame_ts is not None:
                metrics.set_last_frame_age(args.camera_id, args.profile, now - last_frame_ts)

            if frame is None:
                consecutive_read_failures += 1
                metrics.inc_decode_fail(args.camera_id, args.profile)

                if consecutive_read_failures == 1 or consecutive_read_failures % 25 == 0:
                    print(
                        f"[WARN] No frame available; consecutive_timeouts={consecutive_read_failures}; "
                        f"worker_read_failures={capture.read_failures}"
                    )

                if args.exit_on_no_frames:
                    if last_frame_ts is None and (now - t_start) >= args.startup_timeout_sec:
                        print(f"[ERROR] No first frame received within {args.startup_timeout_sec:.1f}s; exiting receiver")
                        exit_code = 2
                        break
                    if last_frame_ts is not None and (now - last_frame_ts) >= args.no_frame_timeout_sec:
                        print(f"[ERROR] No frames received for {args.no_frame_timeout_sec:.1f}s; exiting receiver")
                        exit_code = 3
                        break

                # Keep GUI responsive even when no new frame is available.
                if args.display:
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        print("[INFO] Exit requested by user")
                        break
                continue

            consecutive_read_failures = 0
            last_frame_ts = now
            metrics.set_last_frame_age(args.camera_id, args.profile, 0.0)

            frames_total += 1
            frames_interval += 1
            metrics.inc_frame(args.camera_id, args.profile)
            frame_buffer.append(frame.copy())

            infer_ms = model.infer(frame)
            if infer_ms is not None:
                metrics.observe_infer(args.camera_id, Path(args.model).name if args.model else "generic", infer_ms)

            is_motion, motion_score = motion.detect(frame)
            if is_motion:
                event_id = f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
                keyframe_path = save_keyframe(frame, args.keyframe_dir, event_id)
                buffered = list(frame_buffer)
                clip_path = save_clip(buffered, args.clip_dir, args.camera_id, profile["fps"], event_id)
                clip_id = None
                if clip_path:
                    clip_id = f"clip_{event_id}"
                    event_store.insert_clip({
                        "clip_id": clip_id, "camera_id": args.camera_id,
                        "start_ts": now_iso(), "end_ts": now_iso(), "path": clip_path,
                        "keyframe_path": keyframe_path, "duration_sec": len(buffered) / float(profile["fps"]),
                    })
                event_obj = {
                    "event_id": event_id, "camera_id": args.camera_id, "clip_id": clip_id,
                    "ts": now_iso(), "event_type": "motion_detected", "severity": "info",
                    "label": "motion", "confidence": min(motion_score / max(args.motion_threshold, 1.0), 1.0),
                    "attrs": {"motion_score": motion_score, "profile": args.profile},
                    "caption": f"Motion detected on {args.camera_id} with score {motion_score:.2f}.",
                    "keyframe_path": keyframe_path, "clip_path": clip_path,
                }
                write_jsonl(args.event_log, {"ts": time.time(), "event": "motion_detected", **event_obj})
                event_store.insert_event(event_obj)
                metrics.inc_event(args.camera_id, "motion_detected")
                print(f"[EVENT] motion_detected event_id={event_id} score={motion_score:.2f} keyframe={keyframe_path} clip={clip_path}")

            live_fps = frames_interval / max(now - t_last_report, 1e-9)
            if args.display:
                cv2.imshow(args.window_name, draw_overlay(frame, args.profile, live_fps, infer_ms))
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    print("[INFO] Exit requested by user")
                    break

            if now - t_last_report >= args.report_interval:
                fps = frames_interval / max(now - t_last_report, 1e-9)
                metrics.set_fps(args.camera_id, args.profile, fps)
                print(f"[INFO] profile={args.profile}, FPS={fps:.2f}, frame={frame.shape}, infer_ms={infer_ms}")
                write_jsonl(
                    args.event_log,
                    {
                        "ts": now, "iso_ts": now_iso(), "event": "receiver_fps",
                        "camera_id": args.camera_id, "profile": args.profile, "fps": fps,
                        "frame_shape": list(frame.shape), "infer_ms": infer_ms,
                        "frames_total": frames_total,
                    },
                )
                frames_interval = 0
                t_last_report = now
    finally:
        print("[INFO] Releasing receiver resources...")
        try:
            capture.stop()
        except Exception as exc:
            print(f"[WARN] capture.stop() failed: {exc}")
        try:
            cap.release()
        except Exception as exc:
            print(f"[WARN] cap.release() failed: {exc}")
        try:
            capture.join(timeout=1.0)
            if capture.thread.is_alive():
                print("[WARN] Capture worker did not exit within 1s; continuing because it is a daemon thread")
        except Exception as exc:
            print(f"[WARN] capture.join() failed: {exc}")
        if args.display:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except Exception as exc:
                print(f"[WARN] cv2.destroyAllWindows() failed: {exc}")
        event_store.close()
        write_jsonl(
            args.event_log,
            {
                "ts": time.time(), "iso_ts": now_iso(), "event": "receiver_stopped",
                "camera_id": args.camera_id, "profile": args.profile,
                "frames_total": frames_total, "runtime_sec": time.time() - t_start,
                "exit_code": exit_code,
            },
        )
        print(f"[INFO] Receiver stopped. frames_total={frames_total}, exit_code={exit_code}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
