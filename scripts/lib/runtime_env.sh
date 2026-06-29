#!/usr/bin/env bash
set -euo pipefail

_ai_camera_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_CAMERA_REPO_ROOT_DEFAULT="$(cd "${_ai_camera_script_dir}/../.." && pwd)"
export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$AI_CAMERA_REPO_ROOT_DEFAULT}"

AI_CAMERA_ENV_FILE="${AI_CAMERA_ENV_FILE:-${AI_CAMERA_REPO_ROOT}/deploy/ai-camera.env}"
if [[ -f "$AI_CAMERA_ENV_FILE" ]]; then
  # Preserve any deployment values already exported by the caller so command-line
  # validation can temporarily override deploy/ai-camera.env without editing it.
  # The env file still supplies defaults for variables that were not set.
  declare -A _ai_camera_caller_env=()
  while IFS= read -r _ai_camera_name; do
    case "$_ai_camera_name" in
      AI_CAMERA_*|GRAFANA_*|GF_*) _ai_camera_caller_env["$_ai_camera_name"]="${!_ai_camera_name}" ;;
    esac
  done < <(printf '%s\n' $(compgen -v AI_CAMERA_) $(compgen -v GRAFANA_) $(compgen -v GF_))

  set -a
  # shellcheck disable=SC1090
  source "$AI_CAMERA_ENV_FILE"
  set +a

  for _ai_camera_name in "${!_ai_camera_caller_env[@]}"; do
    export "$_ai_camera_name=${_ai_camera_caller_env[$_ai_camera_name]}"
  done
  unset _ai_camera_name _ai_camera_caller_env
fi

export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$AI_CAMERA_REPO_ROOT_DEFAULT}"
export AI_CAMERA_VENV_DIR="${AI_CAMERA_VENV_DIR:-.venv}"
export AI_CAMERA_NODE1_API_PORT="${AI_CAMERA_NODE1_API_PORT:-8080}"
export AI_CAMERA_NODE1_RTP_PORT="${AI_CAMERA_NODE1_RTP_PORT:-5000}"
export AI_CAMERA_CAPTURE_UDP_PORT="${AI_CAMERA_CAPTURE_UDP_PORT:-5001}"
export AI_CAMERA_NODE1_METRICS_PORT="${AI_CAMERA_NODE1_METRICS_PORT:-9101}"
export AI_CAMERA_NODE2_API_PORT="${AI_CAMERA_NODE2_API_PORT:-8082}"
export AI_CAMERA_CAMERA_ID="${AI_CAMERA_CAMERA_ID:-c922_node2_gate}"
export AI_CAMERA_DEVICE="${AI_CAMERA_DEVICE:-/dev/video0}"
export AI_CAMERA_PROFILE="${AI_CAMERA_PROFILE:-mjpeg_720p30}"
export AI_CAMERA_TRANSPORT="${AI_CAMERA_TRANSPORT:-rtp}"
export AI_CAMERA_DB="${AI_CAMERA_DB:-data/events/ai_camera.db}"
export AI_CAMERA_MIGRATIONS="${AI_CAMERA_MIGRATIONS:-migrations}"
export AI_CAMERA_POLICY="${AI_CAMERA_POLICY:-configs/runtime/security_policy.yaml}"
export AI_CAMERA_NODES_CONFIG="${AI_CAMERA_NODES_CONFIG:-configs/runtime/nodes.yaml}"
export AI_CAMERA_CLIP_ROOT="${AI_CAMERA_CLIP_ROOT:-data/clips}"
export AI_CAMERA_KEYFRAME_ROOT="${AI_CAMERA_KEYFRAME_ROOT:-data/keyframes}"
export AI_CAMERA_DATASET_ROOT="${AI_CAMERA_DATASET_ROOT:-data/datasets}"
export AI_CAMERA_EVENT_LOG="${AI_CAMERA_EVENT_LOG:-results/node1/events.jsonl}"
export AI_CAMERA_LATENCY_THRESHOLD_MS="${AI_CAMERA_LATENCY_THRESHOLD_MS:-5.0}"
export AI_CAMERA_LATENCY_WINDOW_SAMPLES="${AI_CAMERA_LATENCY_WINDOW_SAMPLES:-120}"
export AI_CAMERA_CAPTURE_MAX_DURATION_SEC="${AI_CAMERA_CAPTURE_MAX_DURATION_SEC:-7200}"
export AI_CAMERA_CAPTURE_DEFAULT_DURATION_SEC="${AI_CAMERA_CAPTURE_DEFAULT_DURATION_SEC:-60}"
export AI_CAMERA_CAPTURE_DEFAULT_FRAME_STRIDE="${AI_CAMERA_CAPTURE_DEFAULT_FRAME_STRIDE:-1}"
export AI_CAMERA_MODEL_DIR="${AI_CAMERA_MODEL_DIR:-models/object_detection}"
export AI_CAMERA_YOLO_MODEL="${AI_CAMERA_YOLO_MODEL:-${AI_CAMERA_MODEL_DIR}/yolo11n.onnx}"
export AI_CAMERA_YOLO_MODEL_URL="${AI_CAMERA_YOLO_MODEL_URL:-https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx}"
export AI_CAMERA_YOLO_MODEL_SHA256="${AI_CAMERA_YOLO_MODEL_SHA256:-}"

# Step 16 observability hardening defaults.  The Docker stack binds to
# localhost by default for lab safety, while still using a deterministic
# admin password unless the operator supplies a stronger value in
# deploy/ai-camera.env or the shell environment.  Customer deployments should
# override GRAFANA_ADMIN_PASSWORD and, only when LAN dashboard access is
# intended, set AI_CAMERA_OBSERVABILITY_BIND to the Node1 LAN IP or 0.0.0.0.
export AI_CAMERA_OBSERVABILITY_BIND="${AI_CAMERA_OBSERVABILITY_BIND:-127.0.0.1}"
export AI_CAMERA_PROMETHEUS_RETENTION="${AI_CAMERA_PROMETHEUS_RETENTION:-15d}"
export GRAFANA_ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}"
export GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}"
export AI_CAMERA_GRAFANA_SYNC_ADMIN_PASSWORD="${AI_CAMERA_GRAFANA_SYNC_ADMIN_PASSWORD:-1}"
export GF_AUTH_ANONYMOUS_ENABLED="${GF_AUTH_ANONYMOUS_ENABLED:-false}"
export GF_SECURITY_ALLOW_EMBEDDING="${GF_SECURITY_ALLOW_EMBEDDING:-false}"

export AI_CAMERA_NODE2_WATCHER_SAMPLE_FPS="${AI_CAMERA_NODE2_WATCHER_SAMPLE_FPS:-5}"
export AI_CAMERA_NODE2_WATCHER_MOTION_THRESHOLD="${AI_CAMERA_NODE2_WATCHER_MOTION_THRESHOLD:-12}"
export AI_CAMERA_NODE2_WATCHER_CANDIDATE_WINDOW="${AI_CAMERA_NODE2_WATCHER_CANDIDATE_WINDOW:-5}"
export AI_CAMERA_NODE2_WATCHER_REQUIRED_CONFIRMATIONS="${AI_CAMERA_NODE2_WATCHER_REQUIRED_CONFIRMATIONS:-2}"
export AI_CAMERA_NODE2_WATCHER_COOLDOWN_SEC="${AI_CAMERA_NODE2_WATCHER_COOLDOWN_SEC:-20}"
export AI_CAMERA_NODE2_WATCHER_REQUIRE_YOLO="${AI_CAMERA_NODE2_WATCHER_REQUIRE_YOLO:-1}"
export AI_CAMERA_NODE2_WATCHER_YOLO_MODEL="${AI_CAMERA_NODE2_WATCHER_YOLO_MODEL:-${AI_CAMERA_YOLO_MODEL}}"
export AI_CAMERA_NODE2_WATCHER_YOLO_INPUT_SIZE="${AI_CAMERA_NODE2_WATCHER_YOLO_INPUT_SIZE:-640}"
export AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE="${AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE:-0.45}"
export AI_CAMERA_NODE2_WATCHER_YOLO_IOU="${AI_CAMERA_NODE2_WATCHER_YOLO_IOU:-0.45}"
export AI_CAMERA_NODE2_WATCHER_CLASSES="${AI_CAMERA_NODE2_WATCHER_CLASSES:-person,bicycle,car,motorcycle,bus,truck,cat,dog,backpack,suitcase}"
export AI_CAMERA_NODE2_WATCHER_MAX_DETECTIONS="${AI_CAMERA_NODE2_WATCHER_MAX_DETECTIONS:-20}"

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
