#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
PYTHON_BIN="${PYTHON_BIN:-python}"
export PYTHONNOUSERSITE=1
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

echo "[CI:NODE2] Dependency imports"
"$PYTHON_BIN" - <<'PY'
import site
import sys
print('python', sys.executable)
print('ENABLE_USER_SITE', site.ENABLE_USER_SITE)
if site.ENABLE_USER_SITE:
    raise SystemExit('Node2 runtime must disable user-site packages with PYTHONNOUSERSITE=1')
if any('/.local/' in p for p in sys.path):
    raise SystemExit('Node2 runtime sys.path includes ~/.local user-site packages')
for name in ('yaml', 'fastapi', 'uvicorn', 'pydantic', 'prometheus_client', 'httpx', 'httpx2'):
    __import__(name)
    print(name, 'OK')
import anyio
import anyio._core._tasks as anyio_tasks
import anyio._backends._asyncio  # noqa: F401
print('anyio', anyio.__file__)
if not hasattr(anyio_tasks, 'TaskHandle'):
    raise SystemExit('Broken AnyIO install: missing TaskHandle')
PY

echo "[CI:NODE2] Controller import and profile commands"
"$PYTHON_BIN" - <<'PY'
import os
from agents.node2.node2_streamer_controller import PROFILES, build_gstreamer_command
from agents.node2.node2_timed_jpeg_sender import build_ffmpeg_command
from services.common.timed_frame_protocol import fragment_jpeg_frame, TimedFrameReassembler
for profile in sorted(PROFILES):
    cmd = build_gstreamer_command(profile, os.getenv('AI_CAMERA_TEST_NODE1_IP', '192.0.2.21'), 5000, '/dev/video0')
    joined = ' '.join(cmd)
    print(profile, '=>', joined)
    if profile.startswith('mjpeg') and 'rtpjpegpay' not in joined:
        raise SystemExit(f'{profile} missing rtpjpegpay')
    if profile == 'yuyv_640x480' and ('videoconvert' not in joined or 'format=UYVY' not in joined or 'rtpvrawpay' not in joined):
        raise SystemExit('yuyv_640x480 raw RTP profile is invalid')
cmd = build_ffmpeg_command('mjpeg_720p30', '/dev/video0')
joined = ' '.join(cmd)
print('timed_jpeg_udp mjpeg_720p30 =>', joined)
if 'ffmpeg' not in cmd[0] or '-f' not in cmd or 'image2pipe' not in joined:
    raise SystemExit('timestamped JPEG ffmpeg sender command is invalid')
packets = list(fragment_jpeg_frame(b'\xff\xd8test\xff\xd9', 1, sender_wall_ns=1, sender_monotonic_ns=2, max_payload=4))
reasm = TimedFrameReassembler()
assert any(reasm.push(p) is not None for p in packets)
print('timestamped JPEG protocol OK')
print('Node2 profiles OK')
PY

echo "[CI:NODE2] FastAPI control app import"
"$PYTHON_BIN" - <<'PY'
import services.node2_control_agent.app as app
print('Node2 control app import OK:', app.app.title)
PY

echo "[CI:NODE2] Optional camera presence"
if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-devices || true
else
  echo "v4l2-ctl not installed; skipping camera probe"
fi

echo "[CI:NODE2] Runtime validation PASS"
