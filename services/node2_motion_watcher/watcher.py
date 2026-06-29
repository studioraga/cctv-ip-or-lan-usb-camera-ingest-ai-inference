from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import urlparse

import httpx

from agents.node2.node2_streamer_controller import PROFILES
from services.common.request_signing import signed_headers

LOG = logging.getLogger("node2_motion_watcher")

COCO_CLASS_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

DEFAULT_INTERESTING_LABELS = (
    "person", "bicycle", "car", "motorcycle", "bus", "truck", "cat", "dog", "backpack", "suitcase"
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or value == "" else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None or value == "" else float(value)


def _csv(value: str | None, default: Sequence[str]) -> tuple[str, ...]:
    if not value:
        return tuple(default)
    return tuple(x.strip() for x in value.split(",") if x.strip())


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


@dataclass(frozen=True)
class WatcherConfig:
    node1_url: str
    camera_id: str
    profile: str
    device: str
    duration_sec: int = 60
    udp_port: int = 5001
    frame_stride: int = 1
    requested_by: str = "node2_motion_watcher"
    motion_source: str = "node2_yolo_motion_watcher"
    live_mp4_fps: float = 15.0
    live_mp4_width: int = 640
    sample_fps: float = 5.0
    motion_threshold: float = 12.0
    motion_resize_width: int = 320
    motion_resize_height: int = 180
    candidate_window: int = 5
    required_confirmations: int = 2
    cooldown_sec: float = 20.0
    session_poll_interval_sec: float = 2.0
    node1_timeout_sec: float = 10.0
    max_session_wait_extra_sec: float = 60.0
    yolo_model: str = ""
    yolo_model_id: str = "node2-watcher-yolo11n-coco-onnx"
    yolo_model_sha256: str = ""
    onnx_provider: str = "auto"
    node1_api_key: str = ""
    signing_secret: str = ""
    yolo_input_size: int = 640
    yolo_confidence_threshold: float = 0.45
    yolo_iou_threshold: float = 0.45
    yolo_required: bool = True
    interesting_labels: tuple[str, ...] = field(default_factory=lambda: tuple(DEFAULT_INTERESTING_LABELS))
    max_detections: int = 20
    camera_warmup_frames: int = 3
    camera_release_grace_sec: float = 0.3

    @classmethod
    def from_env(cls) -> "WatcherConfig":
        node1_ip = os.getenv("AI_CAMERA_NODE1_IP", "").strip()
        node1_port = os.getenv("AI_CAMERA_NODE1_API_PORT", "8080").strip()
        node1_url = os.getenv("AI_CAMERA_NODE1_URL", "").strip()
        if not node1_url:
            if not node1_ip:
                node1_ip = "127.0.0.1"
            node1_url = f"http://{node1_ip}:{node1_port}"
        watcher_yolo_model = os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL", "").strip()
        # systemd EnvironmentFile does not expand ${AI_CAMERA_YOLO_MODEL}; treat
        # the example placeholder as unset and fall back to AI_CAMERA_YOLO_MODEL.
        if not watcher_yolo_model or watcher_yolo_model.startswith("${"):
            watcher_yolo_model = os.getenv("AI_CAMERA_YOLO_MODEL", "").strip()
        return cls(
            node1_url=node1_url.rstrip("/"),
            camera_id=os.getenv("AI_CAMERA_CAMERA_ID", "c922_node2_gate"),
            profile=os.getenv("AI_CAMERA_PROFILE", "mjpeg_720p30"),
            device=os.getenv("AI_CAMERA_DEVICE", "/dev/video0"),
            duration_sec=_env_int("AI_CAMERA_MOTION_STREAM_DURATION_SEC", 60),
            udp_port=_env_int("AI_CAMERA_CAPTURE_UDP_PORT", 5001),
            frame_stride=_env_int("AI_CAMERA_CAPTURE_DEFAULT_FRAME_STRIDE", 1),
            live_mp4_fps=_env_float("AI_CAMERA_MOTION_STREAM_LIVE_MP4_FPS", 15.0),
            live_mp4_width=_env_int("AI_CAMERA_MOTION_STREAM_LIVE_MP4_WIDTH", 640),
            sample_fps=_env_float("AI_CAMERA_NODE2_WATCHER_SAMPLE_FPS", 5.0),
            motion_threshold=_env_float("AI_CAMERA_NODE2_WATCHER_MOTION_THRESHOLD", 12.0),
            candidate_window=_env_int("AI_CAMERA_NODE2_WATCHER_CANDIDATE_WINDOW", 5),
            required_confirmations=_env_int("AI_CAMERA_NODE2_WATCHER_REQUIRED_CONFIRMATIONS", 2),
            cooldown_sec=_env_float("AI_CAMERA_NODE2_WATCHER_COOLDOWN_SEC", 20.0),
            yolo_model=watcher_yolo_model,
            yolo_model_id=os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL_ID", "node2-watcher-yolo11n-coco-onnx"),
            yolo_model_sha256=os.getenv("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL_SHA256", os.getenv("AI_CAMERA_YOLO_MODEL_SHA256", "")).strip(),
            onnx_provider=os.getenv("AI_CAMERA_NODE2_WATCHER_ONNX_EXECUTION_PROVIDER", os.getenv("AI_CAMERA_ONNX_EXECUTION_PROVIDER", "auto")),
            node1_api_key=os.getenv("AI_CAMERA_NODE2_TO_NODE1_API_KEY", os.getenv("AI_CAMERA_NODE1_API_TOKEN", "")).strip(),
            signing_secret=os.getenv("AI_CAMERA_NODE_API_SIGNING_SECRET", "").strip(),
            yolo_input_size=_env_int("AI_CAMERA_NODE2_WATCHER_YOLO_INPUT_SIZE", 640),
            yolo_confidence_threshold=_env_float("AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE", 0.45),
            yolo_iou_threshold=_env_float("AI_CAMERA_NODE2_WATCHER_YOLO_IOU", 0.45),
            yolo_required=_env_bool("AI_CAMERA_NODE2_WATCHER_REQUIRE_YOLO", True),
            interesting_labels=_csv(os.getenv("AI_CAMERA_NODE2_WATCHER_CLASSES"), DEFAULT_INTERESTING_LABELS),
            max_detections=_env_int("AI_CAMERA_NODE2_WATCHER_MAX_DETECTIONS", 20),
            camera_warmup_frames=_env_int("AI_CAMERA_NODE2_WATCHER_CAMERA_WARMUP_FRAMES", 3),
            camera_release_grace_sec=_env_float("AI_CAMERA_NODE2_WATCHER_CAMERA_RELEASE_GRACE_SEC", 0.3),
        )


def normalize_detection(det: dict[str, Any]) -> dict[str, Any]:
    attrs = dict(det.get("attrs") or {})
    out: dict[str, Any] = {
        "label": str(det.get("label", "unknown")),
        "confidence": float(det.get("confidence", 0.0)),
    }
    if "bbox_xyxy" in det and det["bbox_xyxy"] is not None:
        out["bbox_xyxy"] = [float(v) for v in det["bbox_xyxy"]]
    if "class_id" in det and det["class_id"] is not None:
        out["class_id"] = int(det["class_id"])
    elif "class_id" in attrs and attrs["class_id"] is not None:
        out["class_id"] = int(attrs["class_id"])
    return out


def build_motion_event_payload(
    cfg: WatcherConfig,
    *,
    motion_score: float,
    detections: Sequence[dict[str, Any]],
    trigger_frame_id: int,
    notes: str = "person/object motion confirmed by Node2 watcher",
) -> dict[str, Any]:
    return {
        "camera_id": cfg.camera_id,
        "profile": cfg.profile,
        "duration_sec": cfg.duration_sec,
        "device": cfg.device,
        "udp_port": cfg.udp_port,
        "frame_stride": cfg.frame_stride,
        "requested_by": cfg.requested_by,
        "notes": notes,
        "motion_score": float(motion_score),
        "motion_source": cfg.motion_source,
        "live_mp4_fps": cfg.live_mp4_fps,
        "live_mp4_width": cfg.live_mp4_width,
        "event_type": "motion_detected",
        "detections": [normalize_detection(d) for d in detections[: cfg.max_detections]],
        "trigger_frame_id": int(trigger_frame_id),
        "trigger_wall_ns": int(time.time_ns()),
        "cooldown_sec": float(cfg.cooldown_sec),
        "model_metadata": {
            "model_id": cfg.yolo_model_id,
            "role": "node2_motion_watcher_confirmation",
            "path": cfg.yolo_model,
            "sha256": cfg.yolo_model_sha256,
            "provider": cfg.onnx_provider,
            "confidence_threshold": cfg.yolo_confidence_threshold,
            "iou_threshold": cfg.yolo_iou_threshold,
            "yolo_required": cfg.yolo_required,
            "interesting_labels": list(cfg.interesting_labels),
        },
    }


class MotionGate:
    """Cheap frame-difference gate to avoid running YOLO on every idle frame."""

    def __init__(self, threshold: float, resize: tuple[int, int] = (320, 180)):
        self.threshold = float(threshold)
        self.resize = resize
        self.prev = None
        try:
            import cv2  # noqa: F401
            import numpy as np  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on Node2 runtime
            raise RuntimeError("MotionGate requires cv2 and numpy; install OpenCV/numpy on Node2") from exc

    def score(self, frame_bgr: Any) -> tuple[float, bool]:
        import cv2
        import numpy as np

        gray = cv2.cvtColor(cv2.resize(frame_bgr, self.resize), cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if self.prev is None:
            self.prev = gray
            return 0.0, False
        diff = cv2.absdiff(self.prev, gray)
        self.prev = gray
        score = float(np.mean(diff))
        return score, score >= self.threshold


class YoloConfirmationDetector:
    """YOLO ONNX confirmation stage using the shared Step 12 detector."""

    def __init__(self, cfg: WatcherConfig):
        self.cfg = cfg
        self.enabled = False
        self.detector = None
        model = cfg.yolo_model.strip()
        if not model:
            if cfg.yolo_required:
                raise RuntimeError("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL or AI_CAMERA_YOLO_MODEL is required")
            LOG.warning("YOLO model path not configured; watcher will use motion-only confirmation")
            return
        model_path = Path(model)
        if not model_path.is_absolute():
            repo = Path(os.getenv("AI_CAMERA_REPO_ROOT", ".")).resolve()
            model_path = repo / model_path
        if not model_path.is_file():
            if cfg.yolo_required:
                raise FileNotFoundError(str(model_path))
            LOG.warning("YOLO model not found at %s; watcher will use motion-only confirmation", model_path)
            return
        from services.common.detectors.yolo_onnx import YoloOnnxDetector

        self.detector = YoloOnnxDetector(
            str(model_path),
            input_size=cfg.yolo_input_size,
            providers=cfg.onnx_provider,
            class_names=COCO_CLASS_NAMES,
            confidence_threshold=cfg.yolo_confidence_threshold,
            iou_threshold=cfg.yolo_iou_threshold,
        )
        self.enabled = True
        LOG.info("Loaded YOLO ONNX model for Node2 watcher: %s", model_path)

    def detect_interesting(self, frame_bgr: Any, *, motion_score: float) -> list[dict[str, Any]]:
        if not self.enabled:
            if self.cfg.yolo_required:
                return []
            return [{"label": "motion", "confidence": min(1.0, motion_score / max(self.cfg.motion_threshold, 1e-6)), "class_id": -1}]
        assert self.detector is not None
        labels = {label.lower() for label in self.cfg.interesting_labels}
        raw_detections = [normalize_detection(det) for det in self.detector.detect(frame_bgr)]
        LOG.debug(
            "raw_yolo_detections_count=%d raw_yolo_detections=%s",
            len(raw_detections),
            raw_detections[: self.cfg.max_detections],
        )
        detections = [
            det for det in raw_detections
            if det["label"].lower() in labels
        ]
        detections.sort(key=lambda d: float(d.get("confidence", 0.0)), reverse=True)
        if raw_detections and not detections:
            LOG.debug("raw_yolo_detections_filtered_out_by_labels=%s interesting_labels=%s", raw_detections[:10], sorted(labels))
        return detections[: self.cfg.max_detections]


class DetectionDebouncer:
    def __init__(self, *, window: int, required: int):
        if window < 1 or required < 1 or required > window:
            raise ValueError("required confirmations must be within the candidate window")
        self.history: deque[bool] = deque(maxlen=window)
        self.required = required

    def update(self, detections: Sequence[dict[str, Any]]) -> bool:
        self.history.append(bool(detections))
        return sum(1 for value in self.history if value) >= self.required

    def reset(self) -> None:
        self.history.clear()


class CameraFrameSource:
    def __init__(self, cfg: WatcherConfig):
        self.cfg = cfg
        self.cap = None

    def open(self) -> None:
        import cv2

        if self.cap is not None:
            self.close()
        self.cap = cv2.VideoCapture(self.cfg.device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            raise RuntimeError(f"unable to open camera device: {self.cfg.device}")
        # Match the C922 MJPEG mode used by the streamer where possible.
        # Some V4L2 webcams silently fall back if the FOURCC is unsupported.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        profile = PROFILES.get(self.cfg.profile, {})
        if profile:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(profile.get("width", 1280)))
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(profile.get("height", 720)))
            self.cap.set(cv2.CAP_PROP_FPS, float(profile.get("fps", 30)))
        for _ in range(max(0, self.cfg.camera_warmup_frames)):
            self.cap.read()

    def read(self) -> Any | None:
        if self.cap is None:
            raise RuntimeError("camera source is not open")
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class Node1MotionClient:
    def __init__(self, cfg: WatcherConfig):
        self.cfg = cfg
        self.client = httpx.Client(timeout=cfg.node1_timeout_sec)

    def _headers(self, method: str, path: str, body: bytes = b"") -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.cfg.node1_api_key:
            headers["X-API-Key"] = self.cfg.node1_api_key
        if self.cfg.signing_secret:
            headers.update(signed_headers(self.cfg.signing_secret, method, path, body))
        return headers

    def post_motion_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = "/motion/events/node2"
        url = f"{self.cfg.node1_url}{path}"
        LOG.info("Posting Node2 motion event to %s", url)
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", **self._headers("POST", path, body)}
        response = self.client.post(url, content=body, headers=headers)
        if response.status_code == 409:
            LOG.warning("Node1 already has an active capture session: %s", response.text[:300])
            return {"status": "already_active", "detail": response.text[:1000]}
        response.raise_for_status()
        return response.json()

    def get_session(self, status_url: str) -> dict[str, Any]:
        url = status_url if status_url.startswith("http") else f"{self.cfg.node1_url}{status_url}"
        path = urlparse(url).path or status_url
        response = self.client.get(url, headers=self._headers("GET", path, b""))
        response.raise_for_status()
        return response.json()

    def wait_for_session_terminal(self, session: dict[str, Any]) -> dict[str, Any]:
        status_url = session.get("status_url") or f"/capture/sessions/{session.get('session_id', '')}"
        deadline = time.monotonic() + self.cfg.duration_sec + self.cfg.max_session_wait_extra_sec
        latest = session
        while time.monotonic() < deadline:
            latest = self.get_session(status_url)
            status = latest.get("status")
            LOG.info("Node1 capture session %s status=%s frames=%s", latest.get("session_id"), status, latest.get("frames_written"))
            if status not in {"pending", "running"}:
                return latest
            time.sleep(self.cfg.session_poll_interval_sec)
        return latest

    def close(self) -> None:
        self.client.close()


class Node2MotionWatcher:
    def __init__(self, cfg: WatcherConfig):
        self.cfg = cfg
        self.motion_gate = MotionGate(cfg.motion_threshold, (cfg.motion_resize_width, cfg.motion_resize_height))
        self.yolo = YoloConfirmationDetector(cfg)
        self.debouncer = DetectionDebouncer(window=cfg.candidate_window, required=cfg.required_confirmations)
        self.source = CameraFrameSource(cfg)
        self.client = Node1MotionClient(cfg)
        self.frame_id = 0

    def close(self) -> None:
        self.source.close()
        self.client.close()

    def run(self, *, one_shot: bool = False) -> None:
        LOG.info("Node2 watcher starting camera=%s profile=%s node1=%s", self.cfg.device, self.cfg.profile, self.cfg.node1_url)
        self.source.open()
        sample_period = 1.0 / max(self.cfg.sample_fps, 0.1)
        try:
            while True:
                loop_started = time.monotonic()
                frame = self.source.read()
                if frame is None:
                    LOG.warning("Camera read failed; retrying")
                    time.sleep(sample_period)
                    continue
                self.frame_id += 1
                motion_score, active_motion = self.motion_gate.score(frame)
                detections: list[dict[str, Any]] = []
                if active_motion:
                    detections = self.yolo.detect_interesting(frame, motion_score=motion_score)
                    confirmed = self.debouncer.update(detections)
                    LOG.info(
                        "motion_score=%.3f active_motion=%s detections=%s debounce=%s/%s confirmed=%s",
                        motion_score,
                        active_motion,
                        detections[:3],
                        sum(1 for value in self.debouncer.history if value),
                        self.cfg.required_confirmations,
                        confirmed,
                    )
                else:
                    confirmed = self.debouncer.update([])
                if detections and confirmed:
                    payload = build_motion_event_payload(
                        self.cfg,
                        motion_score=motion_score,
                        detections=detections,
                        trigger_frame_id=self.frame_id,
                    )
                    # Option A: release /dev/video0 before Node1 asks Node2 streamer to open it.
                    self.source.close()
                    if self.cfg.camera_release_grace_sec > 0:
                        time.sleep(self.cfg.camera_release_grace_sec)
                    session = self.client.post_motion_event(payload)
                    if session.get("session_id"):
                        self.client.wait_for_session_terminal(session)
                    self.debouncer.reset()
                    if one_shot:
                        return
                    LOG.info("Cooldown %.1fs before returning to watch mode", self.cfg.cooldown_sec)
                    time.sleep(self.cfg.cooldown_sec)
                    self.source.open()
                elapsed = time.monotonic() - loop_started
                if elapsed < sample_period:
                    time.sleep(sample_period - elapsed)
        finally:
            self.close()


def synthetic_detection() -> list[dict[str, Any]]:
    return [{"label": "person", "confidence": 0.90, "bbox_xyxy": [220.0, 90.0, 640.0, 710.0], "class_id": 0}]


def run_synthetic_trigger(cfg: WatcherConfig, *, dry_run: bool = False, wait: bool = True) -> dict[str, Any]:
    payload = build_motion_event_payload(
        cfg,
        motion_score=max(cfg.motion_threshold * 1.5, 1.0),
        detections=synthetic_detection(),
        trigger_frame_id=1,
        notes="synthetic Step 15 Node2 watcher validation trigger",
    )
    if dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return payload
    client = Node1MotionClient(cfg)
    try:
        session = client.post_motion_event(payload)
        if wait and session.get("session_id"):
            session = client.wait_for_session_terminal(session)
        print(json.dumps(session, indent=2, sort_keys=True))
        return session
    finally:
        client.close()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Node2 motion/person/object watcher for Node1-managed live MP4 capture")
    ap.add_argument("--node1-url", help="Node1 API base URL, e.g. http://192.168.29.20:8080")
    ap.add_argument("--camera-id")
    ap.add_argument("--profile", choices=sorted(PROFILES))
    ap.add_argument("--device")
    ap.add_argument("--duration-sec", type=int)
    ap.add_argument("--sample-fps", type=float)
    ap.add_argument("--motion-threshold", type=float)
    ap.add_argument("--yolo-model")
    ap.add_argument("--yolo-model-id")
    ap.add_argument("--onnx-provider")
    ap.add_argument("--node1-api-key")
    ap.add_argument("--signing-secret")
    ap.add_argument("--yolo-confidence", type=float, help="YOLO detection confidence threshold")
    ap.add_argument("--yolo-iou", type=float, help="YOLO NMS IoU threshold")
    ap.add_argument("--candidate-window", type=int, help="debounce window length")
    ap.add_argument("--required-confirmations", type=int, help="positive detections required inside the debounce window")
    ap.add_argument("--cooldown-sec", type=float, help="seconds to wait after a completed trigger/session")
    ap.add_argument("--classes", help="comma-separated interesting YOLO labels, e.g. person,car,dog")
    ap.add_argument("--max-detections", type=int, help="maximum detections to include in the Node1 event")
    ap.add_argument("--udp-port", type=int, help="Node1 timed_jpeg_udp capture port")
    ap.add_argument("--frame-stride", type=int, help="source JPEG frame stride for Node1 capture")
    ap.add_argument("--live-mp4-fps", type=float, help="live MP4 output FPS on Node1")
    ap.add_argument("--live-mp4-width", type=int, help="live MP4 output width on Node1")
    ap.add_argument("--camera-release-grace-sec", type=float, help="delay after releasing /dev/video0 before calling Node1")
    ap.add_argument("--no-require-yolo", action="store_true", help="allow motion-only triggering when the YOLO model is not available")
    ap.add_argument("--one-shot", action="store_true", help="exit after one confirmed trigger/session")
    ap.add_argument("--synthetic-trigger", action="store_true", help="post a synthetic person detection event without opening the camera")
    ap.add_argument("--dry-run", action="store_true", help="print the synthetic payload and do not call Node1")
    ap.add_argument("--no-wait", action="store_true", help="do not wait for Node1 session completion after triggering")
    ap.add_argument("--log-level", default=os.getenv("AI_CAMERA_NODE2_WATCHER_LOG_LEVEL", "INFO"))
    return ap.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> WatcherConfig:
    cfg = WatcherConfig.from_env()
    updates: dict[str, Any] = {}
    for field_name, arg_name in [
        ("node1_url", "node1_url"),
        ("camera_id", "camera_id"),
        ("profile", "profile"),
        ("device", "device"),
        ("duration_sec", "duration_sec"),
        ("sample_fps", "sample_fps"),
        ("motion_threshold", "motion_threshold"),
        ("yolo_model", "yolo_model"),
        ("yolo_model_id", "yolo_model_id"),
        ("onnx_provider", "onnx_provider"),
        ("node1_api_key", "node1_api_key"),
        ("signing_secret", "signing_secret"),
        ("yolo_confidence_threshold", "yolo_confidence"),
        ("yolo_iou_threshold", "yolo_iou"),
        ("candidate_window", "candidate_window"),
        ("required_confirmations", "required_confirmations"),
        ("cooldown_sec", "cooldown_sec"),
        ("max_detections", "max_detections"),
        ("udp_port", "udp_port"),
        ("frame_stride", "frame_stride"),
        ("live_mp4_fps", "live_mp4_fps"),
        ("live_mp4_width", "live_mp4_width"),
        ("camera_release_grace_sec", "camera_release_grace_sec"),
    ]:
        value = getattr(args, arg_name)
        if value is not None:
            updates[field_name] = value.rstrip("/") if field_name == "node1_url" else value
    if args.classes is not None:
        updates["interesting_labels"] = _csv(args.classes, DEFAULT_INTERESTING_LABELS)
    if args.no_require_yolo:
        updates["yolo_required"] = False
    return WatcherConfig(**{**cfg.__dict__, **updates})


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = config_from_args(args)
    if cfg.profile not in PROFILES:
        raise SystemExit(f"Unknown profile: {cfg.profile}")
    if args.synthetic_trigger:
        run_synthetic_trigger(cfg, dry_run=args.dry_run, wait=not args.no_wait)
        return 0
    watcher = Node2MotionWatcher(cfg)
    watcher.run(one_shot=args.one_shot)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
