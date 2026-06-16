#!/usr/bin/env python3
"""Node2 timestamped JPEG/UDP sender.

This opt-in sender is used for true sender timestamp + frame_id correlation.
It captures MJPEG frames from V4L2 through ffmpeg, fragments each JPEG frame,
and sends fragments to Node1 using services.common.timed_frame_protocol.
"""
from __future__ import annotations

import argparse
import signal
import socket
import subprocess
import sys
import time
from typing import Iterator

from agents.node2.node2_streamer_controller import PROFILES
from services.common.timed_frame_protocol import DEFAULT_MTU_PAYLOAD, fragment_jpeg_frame

RUNNING = True


def _signal_handler(signum, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def build_ffmpeg_command(profile: str, device: str) -> list[str]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    p = PROFILES[profile]
    if p.get("kind") != "mjpeg":
        raise ValueError("timestamped JPEG transport currently supports MJPEG profiles only")
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "v4l2",
        "-input_format", "mjpeg",
        "-framerate", str(p["fps"]),
        "-video_size", f"{p['width']}x{p['height']}",
        "-i", device,
        "-an",
        "-c:v", "copy",
        "-f", "image2pipe",
        "pipe:1",
    ]


def iter_jpegs_from_pipe(stream, chunk_size: int = 65536) -> Iterator[bytes]:
    """Yield complete JPEG byte strings from an image2pipe stream."""
    buf = bytearray()
    while RUNNING:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        while True:
            soi = buf.find(b"\xff\xd8")
            if soi < 0:
                # Keep at most one byte in case it is the first byte of SOI.
                del buf[:-1]
                break
            if soi > 0:
                del buf[:soi]
            eoi = buf.find(b"\xff\xd9", 2)
            if eoi < 0:
                break
            end = eoi + 2
            jpeg = bytes(buf[:end])
            del buf[:end]
            yield jpeg


def main() -> int:
    ap = argparse.ArgumentParser(description="Node2 timestamped JPEG/UDP sender")
    ap.add_argument("--node1-ip", required=True)
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="mjpeg_720p30")
    ap.add_argument("--max-payload", type=int, default=DEFAULT_MTU_PAYLOAD)
    ap.add_argument("--frame-limit", type=int, default=0, help="optional test limit; 0 means unlimited")
    args = ap.parse_args()

    cmd = build_ffmpeg_command(args.profile, args.device)
    print("[INFO] Starting timestamped JPEG sender", flush=True)
    print(f"[INFO] Profile={args.profile} device={args.device} target={args.node1_ip}:{args.port}", flush=True)
    print("[INFO] " + " ".join(cmd), flush=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_id = 0
    try:
        if proc.stdout is None:
            raise RuntimeError("ffmpeg stdout pipe unavailable")
        for jpeg in iter_jpegs_from_pipe(proc.stdout):
            if not RUNNING:
                break
            frame_id += 1
            sender_wall_ns = time.time_ns()
            sender_monotonic_ns = time.monotonic_ns()
            for packet in fragment_jpeg_frame(
                jpeg,
                frame_id=frame_id,
                sender_wall_ns=sender_wall_ns,
                sender_monotonic_ns=sender_monotonic_ns,
                max_payload=args.max_payload,
            ):
                sock.sendto(packet, (args.node1_ip, args.port))
            if frame_id % 30 == 0:
                print(f"[INFO] sent frame_id={frame_id} bytes={len(jpeg)}", flush=True)
            if args.frame_limit and frame_id >= args.frame_limit:
                break
    except BrokenPipeError:
        return 2
    finally:
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        sock.close()
        print(f"[INFO] timestamped sender stopped frames={frame_id}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
