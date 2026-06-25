#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="${AI_CAMERA_ENV_FILE:-$REPO_ROOT/deploy/ai-camera.env}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export PYTHONNOUSERSITE=1

PY="$(ai_camera_python)"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtualenv python not found: $PY" >&2
  echo "Run scripts/node2/setup_node2_venv.sh first." >&2
  exit 1
fi

exec "$PY" -m agents.node2.node2_motion_watcher "$@"
