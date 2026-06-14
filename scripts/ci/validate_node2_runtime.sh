#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

echo "[CI:NODE2] Dependency imports"
"$PYTHON_BIN" - <<'PY'
for name in ('yaml', 'fastapi', 'uvicorn', 'pydantic', 'prometheus_client', 'httpx', 'httpx2'):
    __import__(name)
    print(name, 'OK')
PY

echo "[CI:NODE2] Controller import and profile commands"
"$PYTHON_BIN" - <<'PY'
import os
from agents.node2.node2_streamer_controller import PROFILES, build_gstreamer_command
for profile in sorted(PROFILES):
    cmd = build_gstreamer_command(profile, os.getenv('AI_CAMERA_TEST_NODE1_IP', '192.0.2.21'), 5000, '/dev/video0')
    joined = ' '.join(cmd)
    print(profile, '=>', joined)
    if profile.startswith('mjpeg') and 'rtpjpegpay' not in joined:
        raise SystemExit(f'{profile} missing rtpjpegpay')
    if profile == 'yuyv_640x480' and ('videoconvert' not in joined or 'format=UYVY' not in joined or 'rtpvrawpay' not in joined):
        raise SystemExit('yuyv_640x480 raw RTP profile is invalid')
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
