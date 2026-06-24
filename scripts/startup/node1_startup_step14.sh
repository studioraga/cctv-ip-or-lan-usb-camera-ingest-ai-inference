#!/usr/bin/env bash
set -euo pipefail

usage(){
  cat <<'USAGE'
Usage: scripts/startup/node1_startup_step14.sh [--duration-sec N]

Starts the validated Step 14 motion-triggered live MP4 validation from Node1:
  - confirms Node1/Node2 health
  - posts a Node2-style motion event into Node1 API
  - records a bounded MP4-capable capture session
  - verifies live.mp4 and preview.mp4 artifacts
  - prints LAN viewing URLs

Options:
  --duration-sec N  override AI_CAMERA_STEP14_TEST_DURATION_SEC for this run
  -h, --help        show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration-sec) export AI_CAMERA_STEP14_TEST_DURATION_SEC="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

mkdir -p results/startup
LOG_FILE="results/startup/node1_startup_step14_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Node1 Step 14 startup ==="
echo "repo=$REPO_ROOT"
echo "log=$LOG_FILE"

if [[ -f deploy/ai-camera.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source deploy/ai-camera.env
  set +a
fi
# shellcheck disable=SC1091
source scripts/lib/runtime_env.sh

echo "NODE1=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}"
echo "NODE2=${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}"
echo "duration=${AI_CAMERA_STEP14_TEST_DURATION_SEC:-${AI_CAMERA_MOTION_STREAM_DURATION_SEC:-60}}"

./scripts/validate_step14_motion_live_mp4.sh

echo "[OK] Node1 Step 14 startup complete. Log: $LOG_FILE"
