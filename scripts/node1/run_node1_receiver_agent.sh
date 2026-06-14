#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"; cd "$AI_CAMERA_REPO_ROOT"
mkdir -p "$(dirname "$(ai_camera_abs_path "$AI_CAMERA_EVENT_LOG")")"
exec "$(ai_camera_python)" -m agents.node1.node1_receiver_agent --profile "$AI_CAMERA_PROFILE" --port "$AI_CAMERA_NODE1_RTP_PORT" --camera-id "$AI_CAMERA_CAMERA_ID" --db-path "$(ai_camera_abs_path "$AI_CAMERA_DB")" --metrics --metrics-port "$AI_CAMERA_NODE1_METRICS_PORT" --motion-events --event-log "$(ai_camera_abs_path "$AI_CAMERA_EVENT_LOG")" "$@"
