#!/usr/bin/env bash
set -euo pipefail

_ai_camera_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_CAMERA_REPO_ROOT_DEFAULT="$(cd "${_ai_camera_script_dir}/../.." && pwd)"
export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$AI_CAMERA_REPO_ROOT_DEFAULT}"

AI_CAMERA_ENV_FILE="${AI_CAMERA_ENV_FILE:-${AI_CAMERA_REPO_ROOT}/deploy/ai-camera.env}"
if [[ -f "$AI_CAMERA_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_CAMERA_ENV_FILE"
  set +a
fi

export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$AI_CAMERA_REPO_ROOT_DEFAULT}"
export AI_CAMERA_VENV_DIR="${AI_CAMERA_VENV_DIR:-.venv}"
export AI_CAMERA_NODE1_API_PORT="${AI_CAMERA_NODE1_API_PORT:-8080}"
export AI_CAMERA_NODE1_RTP_PORT="${AI_CAMERA_NODE1_RTP_PORT:-5000}"
export AI_CAMERA_NODE1_METRICS_PORT="${AI_CAMERA_NODE1_METRICS_PORT:-9101}"
export AI_CAMERA_NODE2_API_PORT="${AI_CAMERA_NODE2_API_PORT:-8082}"
export AI_CAMERA_CAMERA_ID="${AI_CAMERA_CAMERA_ID:-c922_node2_gate}"
export AI_CAMERA_DEVICE="${AI_CAMERA_DEVICE:-/dev/video0}"
export AI_CAMERA_PROFILE="${AI_CAMERA_PROFILE:-mjpeg_720p30}"
export AI_CAMERA_DB="${AI_CAMERA_DB:-data/events/ai_camera.db}"
export AI_CAMERA_MIGRATIONS="${AI_CAMERA_MIGRATIONS:-migrations}"
export AI_CAMERA_POLICY="${AI_CAMERA_POLICY:-configs/runtime/security_policy.yaml}"
export AI_CAMERA_NODES_CONFIG="${AI_CAMERA_NODES_CONFIG:-configs/runtime/nodes.yaml}"
export AI_CAMERA_CLIP_ROOT="${AI_CAMERA_CLIP_ROOT:-data/clips}"
export AI_CAMERA_KEYFRAME_ROOT="${AI_CAMERA_KEYFRAME_ROOT:-data/keyframes}"
export AI_CAMERA_EVENT_LOG="${AI_CAMERA_EVENT_LOG:-results/node1/events.jsonl}"
export AI_CAMERA_LATENCY_THRESHOLD_MS="${AI_CAMERA_LATENCY_THRESHOLD_MS:-5.0}"
export AI_CAMERA_LATENCY_WINDOW_SAMPLES="${AI_CAMERA_LATENCY_WINDOW_SAMPLES:-120}"

ai_camera_abs_path() {
  local p="$1"
  if [[ "$p" = /* ]]; then printf '%s\n' "$p"; else printf '%s/%s\n' "$AI_CAMERA_REPO_ROOT" "$p"; fi
}

ai_camera_python() {
  printf '%s/%s/bin/python\n' "$AI_CAMERA_REPO_ROOT" "$AI_CAMERA_VENV_DIR"
}

ai_camera_uvicorn() {
  printf '%s/%s/bin/uvicorn\n' "$AI_CAMERA_REPO_ROOT" "$AI_CAMERA_VENV_DIR"
}

ai_camera_primary_ipv4() {
  local iface="${AI_CAMERA_INTERFACE:-}"
  if [[ -n "$iface" ]]; then
    ip -4 -o addr show dev "$iface" scope global | awk '{split($4,a,"/"); print a[1]; exit}'
  else
    ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}'
  fi
}

ai_camera_require_repo() {
  [[ -f "$AI_CAMERA_REPO_ROOT/README.md" ]] || {
    echo "ERROR: AI_CAMERA_REPO_ROOT is not a repository: $AI_CAMERA_REPO_ROOT" >&2; return 1;
  }
}
