#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"; cd "$AI_CAMERA_REPO_ROOT"
: "${AI_CAMERA_NODE1_IP:?Set AI_CAMERA_NODE1_IP in deploy/ai-camera.env}"
exec "$(ai_camera_python)" agents/node2/node2_streamer_controller.py \
  --node1-ip "$AI_CAMERA_NODE1_IP" \
  --port "$AI_CAMERA_NODE1_RTP_PORT" \
  --profile "$AI_CAMERA_PROFILE" "$@"
