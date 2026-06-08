#!/usr/bin/env python3
"""
Node1 Camera Receiver Agent

Receives RTP camera stream from Node2 Jetson/C922 over UDP and exposes:
  - FPS monitoring
  - optional OpenCV display
  - optional ONNX Runtime inference hook
  - JSONL event logging
  - multiple GStreamer receive profiles

Supported receive profiles:
  1. mjpeg_720p30
  2. mjpeg_720p60
  3. mjpeg_1080p30
  4. yuyv_640x480

Important:
  - For RTP/JPEG sender, use MJPEG profiles.
  - For RTP/raw YUYV sender, Node2 must send raw RTP video using rtpvrawpay.
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

import cv2
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None


RUNNING = True


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


PROFILES: Dict[str, Dict[str, Any]] = {
    "mjpeg_720p30": {
        "encoding": "JPEG",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "payload": 26,
        "depay": "rtpjpegdepay",
        "decode": "jpegdec",
        "format": "BGR",
        "description": "RTP/JPEG MJPEG 1280x720@30",
    },
    "mjpeg_720p60": {
        "encoding": "JPEG",
        "width": 1280,
        "height": 720,
        "fps": 60,
        "payload": 26,
        "depay": "rtpjpegdepay",
        "decode": "jpegdec",
        "format": "BGR",
        "description": "RTP/JPEG MJPEG 1280x720@60",
    },
    "mjpeg_1080p30": {
        "encoding": "JPEG",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "payload": 26,
        "depay": "rtpjpegdepay",
        "decode": "jpegdec",
        "format": "BGR",
        "description": "RTP/JPEG MJPEG 1920x1080@30",
    },
    "yuyv_640x480": {
        "encoding": "RAW",
        "width": 640,
        "height": 480,
        "fps": 30,
        "payload": 96,
        "raw_format": "YUY2",
        "format": "BGR",
        "description": "RTP/raw YUYV 640x480@30",
    },
}


def build_mjpeg_pipeline(
    port: int,
    payload: int,
    buffer_size: int,
    use_jitterbuffer: bool,
    jitter_latency_ms: int,
) -> str:
    jitter = ""
    if use_jitterbuffer:
        jitter = (
            f"rtpjitterbuffer latency={jitter_latency_ms} "
            "drop-on-latency=true ! "
        )

    return (
        f'udpsrc port={port} buffer-size={buffer_size} '
        f'caps="application/x-rtp,media=video,clock-rate=90000,'
        f'encoding-name=JPEG,payload={payload}" ! '
        f'{jitter}'
        'queue leaky=downstream max-size-buffers=4 ! '
        'rtpjpegdepay ! '
        'jpegdec ! '
        'videoconvert ! '
        'video/x-raw,format=BGR ! '
        'appsink drop=true sync=false max-buffers=1'
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
    jitter = ""
    if use_jitterbuffer:
        jitter = (
            f"rtpjitterbuffer latency={jitter_latency_ms} "
            "drop-on-latency=true ! "
        )

    return (
        f'udpsrc port={port} buffer-size={buffer_size} '
        f'caps="application/x-rtp,media=video,clock-rate=90000,'
        f'encoding-name=RAW,payload={payload},'
        f'sampling=YCbCr-4:2:2,depth=(string)8,'
        f'width=(string){width},height=(string){height},'
        f'colorimetry=(string)BT601-5,'
        f'a-framerate=(string){fps}.000000" ! '
        f'{jitter}'
        'queue leaky=downstream max-size-buffers=4 ! '
        'rtpvrawdepay ! '
        'videoconvert ! '
        'video/x-raw,format=BGR ! '
        'appsink drop=true sync=false max-buffers=1'
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
        return build_mjpeg_pipeline(
            port=port,
            payload=p["payload"],
            buffer_size=buffer_size,
            use_jitterbuffer=use_jitterbuffer,
            jitter_latency_ms=jitter_latency_ms,
        )

    if p["encoding"] == "RAW":
        return build_yuyv_pipeline(
            port=port,
            payload=p["payload"],
            width=p["width"],
            height=p["height"],
            fps=p["fps"],
            buffer_size=buffer_size,
            use_jitterbuffer=use_jitterbuffer,
            jitter_latency_ms=jitter_latency_ms,
        )

    raise ValueError(f"Unsupported encoding: {p['encoding']}")


def ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def write_event(event_log: Optional[str], event: Dict[str, Any]) -> None:
    if not event_log:
        return

    ensure_parent(event_log)

    with open(event_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


class OptionalOnnxModel:
    def __init__(self, model_path: Optional[str]):
        self.model_path = model_path
        self.session = None
        self.input_name = None

        if not model_path:
            return

        if ort is None:
            raise RuntimeError(
                "onnxruntime is not installed, but --model was provided"
            )

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

        # Generic placeholder preprocessing.
        # Replace this block with model-specific preprocessing.
        resized = cv2.resize(frame, (224, 224))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = rgb.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))
        tensor = np.expand_dims(tensor, axis=0)

        _ = self.session.run(None, {self.input_name: tensor})

        return (time.time() - t0) * 1000.0


def draw_overlay(
    frame: np.ndarray,
    profile_name: str,
    fps: float,
    infer_ms: Optional[float],
) -> np.ndarray:
    overlay = frame.copy()

    text1 = f"Node1 Receiver | {profile_name} | FPS={fps:.2f}"
    text2 = "infer_ms=None" if infer_ms is None else f"infer_ms={infer_ms:.2f}"

    cv2.putText(
        overlay,
        text1,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        overlay,
        text2,
        (20, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    return overlay


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Node1 RTP camera receiver agent"
    )

    parser.add_argument(
        "--profile",
        default="mjpeg_720p30",
        choices=sorted(PROFILES.keys()),
        help="Receiver profile. Must match Node2 sender profile.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="UDP port to receive RTP stream",
    )

    parser.add_argument(
        "--buffer-size",
        type=int,
        default=8 * 1024 * 1024,
        help="UDP socket buffer size for udpsrc",
    )

    parser.add_argument(
        "--display",
        action="store_true",
        help="Show OpenCV display window",
    )

    parser.add_argument(
        "--event-log",
        default="results/node1/events.jsonl",
        help="JSONL event log path",
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Optional ONNX model path",
    )

    parser.add_argument(
        "--report-interval",
        type=float,
        default=2.0,
        help="FPS reporting interval in seconds",
    )

    parser.add_argument(
        "--jitterbuffer",
        action="store_true",
        help="Enable RTP jitterbuffer",
    )

    parser.add_argument(
        "--jitter-latency-ms",
        type=int,
        default=50,
        help="RTP jitterbuffer latency in ms",
    )

    parser.add_argument(
        "--window-name",
        default="Node2 C922 stream on Node1",
        help="OpenCV display window name",
    )

    args = parser.parse_args()

    profile = PROFILES[args.profile]
    pipeline = build_pipeline(
        profile_name=args.profile,
        port=args.port,
        buffer_size=args.buffer_size,
        use_jitterbuffer=args.jitterbuffer,
        jitter_latency_ms=args.jitter_latency_ms,
    )

    print(f"[INFO] Profile: {args.profile}")
    print(f"[INFO] Description: {profile['description']}")
    print("[INFO] Opening pipeline:")
    print(pipeline)

    model = OptionalOnnxModel(args.model)

    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    if not cap.isOpened():
        print("[ERROR] Failed to open GStreamer pipeline", file=sys.stderr)
        return 1

    frames_total = 0
    frames_interval = 0
    t_start = time.time()
    t_last_report = t_start

    write_event(
        args.event_log,
        {
            "ts": time.time(),
            "event": "receiver_started",
            "profile": args.profile,
            "port": args.port,
            "pipeline": pipeline,
        },
    )

    try:
        while RUNNING:
            ok, frame = cap.read()

            if not ok or frame is None:
                print("[WARN] Failed to read frame")
                time.sleep(0.01)
                continue

            frames_total += 1
            frames_interval += 1

            infer_ms = model.infer(frame)

            now = time.time()

            if args.display:
                display_frame = draw_overlay(
                    frame=frame,
                    profile_name=args.profile,
                    fps=frames_interval / max(now - t_last_report, 1e-9),
                    infer_ms=infer_ms,
                )

                cv2.imshow(args.window_name, display_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord("q"):
                    print("[INFO] Exit requested by user")
                    break

            if now - t_last_report >= args.report_interval:
                fps = frames_interval / max(now - t_last_report, 1e-9)

                print(
                    f"[INFO] profile={args.profile}, "
                    f"FPS={fps:.2f}, "
                    f"frame={frame.shape}, "
                    f"infer_ms={infer_ms}"
                )

                write_event(
                    args.event_log,
                    {
                        "ts": now,
                        "event": "receiver_fps",
                        "profile": args.profile,
                        "fps": fps,
                        "frame_shape": list(frame.shape),
                        "infer_ms": infer_ms,
                        "frames_total": frames_total,
                    },
                )

                frames_interval = 0
                t_last_report = now

    finally:
        cap.release()

        if args.display:
            cv2.destroyAllWindows()

        write_event(
            args.event_log,
            {
                "ts": time.time(),
                "event": "receiver_stopped",
                "profile": args.profile,
                "frames_total": frames_total,
                "runtime_sec": time.time() - t_start,
            },
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
