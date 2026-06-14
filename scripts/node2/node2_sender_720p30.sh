#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
: "${AI_CAMERA_NODE1_IP:?Set AI_CAMERA_NODE1_IP in deploy/ai-camera.env}"
exec taskset -c "${AI_CAMERA_CPUSET:-0-3}" gst-launch-1.0 -e \
  v4l2src device="$AI_CAMERA_DEVICE" io-mode=2 ! \
  image/jpeg,width=1280,height=720,framerate=30/1 ! jpegdec ! videoconvert ! video/x-raw,format=NV12 ! \
  nvvidconv ! 'video/x-raw(memory:NVMM),format=NV12' ! \
  nvv4l2h264enc maxperf-enable=1 insert-sps-pps=1 iframeinterval=30 bitrate=4000000 ! \
  h264parse ! rtph264pay config-interval=1 pt=96 ! \
  udpsink host="$AI_CAMERA_NODE1_IP" port="$AI_CAMERA_NODE1_RTP_PORT" sync=false async=false
