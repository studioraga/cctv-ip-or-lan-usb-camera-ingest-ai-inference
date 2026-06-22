#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"; cd "$AI_CAMERA_REPO_ROOT"
NODE2_USER="${AI_CAMERA_NODE2_USER:?Set AI_CAMERA_NODE2_USER in deploy/ai-camera.env}"
NODE2_HOST="${AI_CAMERA_NODE2_HOST:-${AI_CAMERA_NODE2_IP:-}}"; [[ -n "$NODE2_HOST" ]] || { echo 'ERROR: set AI_CAMERA_NODE2_HOST or AI_CAMERA_NODE2_IP' >&2; exit 1; }
REMOTE_ROOT="${AI_CAMERA_NODE2_REMOTE_ROOT:-\$HOME/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference}"
ssh "${NODE2_USER}@${NODE2_HOST}" "mkdir -p '$REMOTE_ROOT'"
rsync -avh --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.venv.backup-*/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache/' \
  --exclude 'results/' \
  --exclude 'data/events/*.db*' \
  --exclude 'data/clips/**' \
  --exclude 'data/keyframes/*' \
  ./ "${NODE2_USER}@${NODE2_HOST}:${REMOTE_ROOT}/"
