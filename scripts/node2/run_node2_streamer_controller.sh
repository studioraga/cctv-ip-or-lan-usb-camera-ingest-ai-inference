#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
source .venv/bin/activate
python agents/node2/node2_streamer_controller.py \
  --node1-ip "${NODE1_IP:-192.168.29.20}" \
  --profile "${PROFILE:-mjpeg_720p30}" \
  "$@"
