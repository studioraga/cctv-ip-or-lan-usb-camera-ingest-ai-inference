#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/models/download_yolo_onnx.sh [--force]

Downloads the default YOLO ONNX model into the repo-local model directory and
persists AI_CAMERA_YOLO_MODEL in deploy/ai-camera.env.

Defaults:
  AI_CAMERA_MODEL_DIR=models/object_detection
  AI_CAMERA_YOLO_MODEL=models/object_detection/yolo11n.onnx
  AI_CAMERA_YOLO_MODEL_URL=https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx

Options:
  --force     re-download even when the target ONNX file already exists
  -h, --help  show this help
USAGE
}

FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="${AI_CAMERA_ENV_FILE:-$REPO_ROOT/deploy/ai-camera.env}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
# Force this checkout even if deploy/ai-camera.env contains an old absolute path.
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"

MODEL_DIR_REL="${AI_CAMERA_MODEL_DIR:-models/object_detection}"
MODEL_PATH_REL="${AI_CAMERA_YOLO_MODEL:-${MODEL_DIR_REL}/yolo11n.onnx}"
MODEL_URL="${AI_CAMERA_YOLO_MODEL_URL:-https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx}"
MODEL_SHA256="${AI_CAMERA_YOLO_MODEL_SHA256:-}"

MODEL_DIR_ABS="$(ai_camera_abs_path "$MODEL_DIR_REL")"
MODEL_PATH_ABS="$(ai_camera_abs_path "$MODEL_PATH_REL")"
TMP_PATH="${MODEL_PATH_ABS}.tmp"
ENV_FILE="$REPO_ROOT/deploy/ai-camera.env"

mkdir -p "$MODEL_DIR_ABS" "$(dirname "$MODEL_PATH_ABS")" "$REPO_ROOT/deploy" results/models

log() { echo "$*" | tee -a "results/models/download_yolo_onnx.log"; }

persist_env_value() {
  local key="$1"
  local value="$2"
  touch "$ENV_FILE"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

if [[ -s "$MODEL_PATH_ABS" && "$FORCE" -eq 0 ]]; then
  log "[OK] YOLO ONNX model already exists: $MODEL_PATH_ABS"
else
  log "=== Download YOLO ONNX model ==="
  log "url=$MODEL_URL"
  log "target=$MODEL_PATH_ABS"
  rm -f "$TMP_PATH"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 --retry-delay 2 -o "$TMP_PATH" "$MODEL_URL"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$TMP_PATH" "$MODEL_URL"
  else
    echo "ERROR: curl or wget is required to download the YOLO ONNX model." >&2
    exit 1
  fi

  if [[ -n "$MODEL_SHA256" ]]; then
    echo "${MODEL_SHA256}  ${TMP_PATH}" | sha256sum -c -
  fi

  if [[ ! -s "$TMP_PATH" ]]; then
    echo "ERROR: downloaded model is empty: $TMP_PATH" >&2
    exit 1
  fi
  mv "$TMP_PATH" "$MODEL_PATH_ABS"
  log "[OK] Downloaded YOLO ONNX model: $MODEL_PATH_ABS"
fi

persist_env_value AI_CAMERA_MODEL_DIR "$MODEL_DIR_REL"
persist_env_value AI_CAMERA_YOLO_MODEL "$MODEL_PATH_REL"
persist_env_value AI_CAMERA_YOLO_MODEL_URL "$MODEL_URL"
if [[ -n "$MODEL_SHA256" ]]; then
  persist_env_value AI_CAMERA_YOLO_MODEL_SHA256 "$MODEL_SHA256"
fi

log "[OK] deploy/ai-camera.env now pins AI_CAMERA_YOLO_MODEL=$MODEL_PATH_REL"
log "export AI_CAMERA_YOLO_MODEL=$MODEL_PATH_REL"
