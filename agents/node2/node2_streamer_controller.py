#!/usr/bin/env python3
"""Node2 camera streamer controller.

Starts a selected GStreamer RTP sender profile from the C922/V4L2 camera
and optionally records tegrastats alongside the run.

Supported profiles:
  - mjpeg_480p30
  - mjpeg_720p30
  - mjpeg_720p60
  - mjpeg_1080p30
  - yuyv_640x480
"""

import argparse
import signal
import subprocess
import time
from pathlib import Path


PROFILES = {
    "mjpeg_480p30": {
        "kind": "mjpeg",
        "width": 640,
        "height": 480,
        "fps": 30,
        "payload": 26,
    },
    "mjpeg_720p30": {
        "kind": "mjpeg",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "payload": 26,
    },
    "mjpeg_720p60": {
        "kind": "mjpeg",
        "width": 1280,
        "height": 720,
        "fps": 60,
        "payload": 26,
    },
    "mjpeg_1080p30": {
        "kind": "mjpeg",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "payload": 26,
    },
    "yuyv_640x480": {
        "kind": "yuyv",
        "width": 640,
        "height": 480,
        "fps": 30,
        "payload": 96,
    },
}


def build_gstreamer_command(profile: str, node1_ip: str, port: int, device: str):
    """Build gst-launch command for selected profile."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")

    p = PROFILES[profile]

    common_prefix = [
        "taskset", "-c", "0-3",
        "gst-launch-1.0", "-v", "-e",
        "v4l2src", f"device={device}", "io-mode=2", "do-timestamp=true",
        "!",
    ]

    common_suffix = [
        "!",
        "udpsink", f"host={node1_ip}", f"port={port}", "sync=false", "async=false",
    ]

    if p["kind"] == "mjpeg":
        return (
            common_prefix
            + [
                f"image/jpeg,width={p['width']},height={p['height']},framerate={p['fps']}/1",
                "!",
                "queue", "leaky=downstream", "max-size-buffers=2",
                "!",
                "rtpjpegpay", f"pt={p['payload']}",
            ]
            + common_suffix
        )
      
    if p["kind"] == "yuyv":
        return (
            common_prefix
            + [
                f"video/x-raw,format=YUY2,width={p['width']},height={p['height']},framerate={p['fps']}/1",
                "!",
                "videoconvert",
                "!",
                "video/x-raw,format=UYVY",
                "!",
                "queue", "leaky=downstream", "max-size-buffers=2",
                "!",
                "rtpvrawpay", f"pt={p['payload']}",
            ]
            + common_suffix
        )    

    raise ValueError(f"Unknown profile kind: {p['kind']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Node2 C922 RTP streamer controller")

    ap.add_argument("--node1-ip", default="192.168.29.20")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="mjpeg_720p30")
    ap.add_argument("--tegrastats", action="store_true")
    ap.add_argument(
        "--tegrastats-log",
        default="results/node2/camera_stream_tegrastats.log",
    )

    args = ap.parse_args()

    ts_proc = None
    ts_file = None

    try:
        if args.tegrastats:
            Path(args.tegrastats_log).parent.mkdir(parents=True, exist_ok=True)
            ts_file = open(args.tegrastats_log, "a", encoding="utf-8")
            ts_proc = subprocess.Popen(
                ["tegrastats"],
                stdout=ts_file,
                stderr=subprocess.STDOUT,
            )

        cmd = build_gstreamer_command(
            profile=args.profile,
            node1_ip=args.node1_ip,
            port=args.port,
            device=args.device,
        )

        print("[INFO] Starting Node2 stream:")
        print("[INFO] Profile:", args.profile)
        print("[INFO]", " ".join(cmd))

        proc = subprocess.Popen(cmd)

        try:
            return proc.wait()
        except KeyboardInterrupt:
            print("\n[INFO] Keyboard interrupt received, stopping stream...")
            proc.send_signal(signal.SIGINT)
            time.sleep(1)

            if proc.poll() is None:
                proc.terminate()

            return 0

    finally:
        if ts_proc:
            ts_proc.terminate()
            try:
                ts_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                ts_proc.kill()

        if ts_file:
            ts_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
