#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
NODE1_IP="${AI_CAMERA_NODE1_IP:?Set AI_CAMERA_NODE1_IP in deploy/ai-camera.env}"; PORT="${AI_CAMERA_NODE1_RTP_PORT:-5000}"; DEVICE="${AI_CAMERA_DEVICE:-/dev/video0}"
echo "[INFO] Sending mjpeg_480p30 from $DEVICE to $NODE1_IP:$PORT"
exec taskset -c "${AI_CAMERA_CPUSET:-0-3}" gst-launch-1.0 -v -e v4l2src device="$DEVICE" io-mode=2 do-timestamp=true ! image/jpeg,width=640,height=480,framerate=30/1 ! rtpjpegpay pt=26 ! udpsink host="$NODE1_IP" port="$PORT" sync=false async=false
