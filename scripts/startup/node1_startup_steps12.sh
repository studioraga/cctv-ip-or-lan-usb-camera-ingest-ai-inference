#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/startup/node1_startup_steps12.sh [--install-deps] [--download-yolo] [--run-validations]

Bootstraps Node1 through the validated Step 12 milestone:
  - creates deploy/ai-camera.env if missing
  - sources current repo-local runtime env
  - optionally installs Node1 dependencies / recreates .venv
  - optionally downloads the default YOLO ONNX model to a fixed repo-local path
  - prepares runtime config, policy, migrations, and tests
  - installs, daemon-reloads, enables, and restarts Node1 systemd units
  - checks Node1 API, Node1 receiver metrics, and Node2 health
  - optionally runs Step 9, Step 11, Step 12 E2E, and Step 12 YOLO validation

Required before first run:
  - edit deploy/ai-camera.env and set AI_CAMERA_NODE2_IP=<Node2 LAN IP>
  - run the matching Node2 startup script first, or ensure Node2 service is already healthy

Options:
  --install-deps     run scripts/node1/install_node1_dependencies.sh first
  --download-yolo    download/pin models/object_detection/yolo11n.onnx before validation
  --run-validations  run validate_step9/11/12 scripts after services are healthy
  -h, --help         show this help
USAGE
}

INSTALL_DEPS=0
DOWNLOAD_YOLO=0
RUN_VALIDATIONS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-deps) INSTALL_DEPS=1 ;;
    --download-yolo) DOWNLOAD_YOLO=1 ;;
    --run-validations) RUN_VALIDATIONS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

wait_for_http() {
  local label="$1"
  local url="$2"
  local service="$3"
  local mode="${4:-json}"
  local attempts="${5:-30}"
  local delay="${6:-1}"
  local tmp_err
  tmp_err="$(mktemp)"

  echo "[WAIT] ${label}: ${url}"
  for i in $(seq 1 "$attempts"); do
    if [[ "$mode" == "json" ]]; then
      if curl -fsS --max-time 2 "$url" 2>"$tmp_err" | python3 -m json.tool; then
        rm -f "$tmp_err"
        echo "[OK] ${label} is healthy"
        return 0
      fi
    else
      if curl -fsS --max-time 2 "$url" >/dev/null 2>"$tmp_err"; then
        rm -f "$tmp_err"
        echo "[OK] ${label} is healthy"
        return 0
      fi
    fi

    if [[ "$service" != "-" ]] && ! systemctl is-active --quiet "$service"; then
      echo "[WARN] ${service} is not active while waiting for ${label}."
      systemctl --no-pager --full status "$service" || true
      journalctl -u "$service" --no-pager -n 80 || true
      rm -f "$tmp_err"
      return 1
    fi

    echo "[WAIT] ${label} not ready yet (${i}/${attempts}): $(cat "$tmp_err")"
    sleep "$delay"
  done

  echo "[FAIL] ${label} did not become healthy after ${attempts} attempts."
  if [[ "$service" != "-" ]]; then
    systemctl --no-pager --full status "$service" || true
    journalctl -u "$service" --no-pager -n 120 || true
  fi
  rm -f "$tmp_err"
  return 1
}

mkdir -p results/startup
LOG_FILE="results/startup/node1_startup_steps12_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Node1 Step 12 startup ==="
echo "repo=$REPO_ROOT"
echo "log=$LOG_FILE"

ENV_FILE="$REPO_ROOT/deploy/ai-camera.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$REPO_ROOT/deploy/ai-camera.env.example" "$ENV_FILE"
  echo "[INFO] Created $ENV_FILE from example. Edit it if Node2 IP is not already exported."
fi

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="$ENV_FILE"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
# Force this checkout even if deploy/ai-camera.env contains an old absolute path.
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export PYTHONNOUSERSITE=1

LOCAL_IP="$(ai_camera_primary_ipv4 || true)"
export AI_CAMERA_NODE1_IP="${AI_CAMERA_NODE1_IP:-$LOCAL_IP}"
if [[ -z "${AI_CAMERA_NODE2_IP:-}" && -n "${AI_CAMERA_NODE2_HOST:-}" ]]; then
  export AI_CAMERA_NODE2_IP="$(getent hosts "$AI_CAMERA_NODE2_HOST" | awk '{print $1; exit}')"
fi
if [[ -z "${AI_CAMERA_NODE1_IP:-}" ]]; then
  echo "ERROR: could not auto-detect Node1 IP. Set AI_CAMERA_NODE1_IP in deploy/ai-camera.env." >&2
  exit 1
fi
if [[ -z "${AI_CAMERA_NODE2_IP:-}" ]]; then
  echo "ERROR: AI_CAMERA_NODE2_IP is required on Node1. Edit deploy/ai-camera.env and set Node2 LAN IP." >&2
  exit 1
fi

echo "NODE1=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT} metrics=${AI_CAMERA_NODE1_METRICS_PORT} rtp=${AI_CAMERA_NODE1_RTP_PORT}"
echo "NODE2=${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}"
echo "YOLO_ONNX=$(ai_camera_abs_path "${AI_CAMERA_YOLO_MODEL:-models/object_detection/yolo11n.onnx}")"

if [[ "$INSTALL_DEPS" -eq 1 || ! -x "$(ai_camera_python)" ]]; then
  echo "=== Install Node1 dependencies / setup venv ==="
  "$REPO_ROOT/scripts/node1/install_node1_dependencies.sh"
fi

PY="$(ai_camera_python)"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtual environment python is missing: $PY" >&2
  exit 1
fi

if [[ "$DOWNLOAD_YOLO" -eq 1 ]]; then
  echo "=== Download / pin YOLO ONNX model ==="
  ./scripts/models/download_yolo_onnx.sh
  # Reload runtime env because download_yolo_onnx.sh may have persisted AI_CAMERA_YOLO_MODEL.
  # shellcheck disable=SC1091
  source "$REPO_ROOT/scripts/lib/runtime_env.sh"
  export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
fi

echo "=== Prepare deployment ==="
./scripts/common/prepare_deployment.sh node1

echo "=== Install Node1 systemd units ==="
sudo env \
  AI_CAMERA_REPO_ROOT="$AI_CAMERA_REPO_ROOT" \
  AI_CAMERA_NODE1_IP="$AI_CAMERA_NODE1_IP" \
  AI_CAMERA_NODE2_IP="$AI_CAMERA_NODE2_IP" \
  AI_CAMERA_NODE1_API_PORT="$AI_CAMERA_NODE1_API_PORT" \
  AI_CAMERA_NODE1_RTP_PORT="$AI_CAMERA_NODE1_RTP_PORT" \
  AI_CAMERA_CAPTURE_UDP_PORT="$AI_CAMERA_CAPTURE_UDP_PORT" \
  AI_CAMERA_NODE1_METRICS_PORT="$AI_CAMERA_NODE1_METRICS_PORT" \
  AI_CAMERA_NODE2_API_PORT="$AI_CAMERA_NODE2_API_PORT" \
  AI_CAMERA_VENV_DIR="$AI_CAMERA_VENV_DIR" \
  AI_CAMERA_POLICY="$AI_CAMERA_POLICY" \
  AI_CAMERA_DB="$AI_CAMERA_DB" \
  AI_CAMERA_MIGRATIONS="$AI_CAMERA_MIGRATIONS" \
  AI_CAMERA_PROFILE="$AI_CAMERA_PROFILE" \
  AI_CAMERA_TRANSPORT="$AI_CAMERA_TRANSPORT" \
  AI_CAMERA_DATASET_ROOT="$AI_CAMERA_DATASET_ROOT" \
  AI_CAMERA_CAPTURE_MAX_DURATION_SEC="$AI_CAMERA_CAPTURE_MAX_DURATION_SEC" \
  AI_CAMERA_CAMERA_ID="$AI_CAMERA_CAMERA_ID" \
  AI_CAMERA_DEVICE="$AI_CAMERA_DEVICE" \
  AI_CAMERA_EVENT_LOG="$AI_CAMERA_EVENT_LOG" \
  AI_CAMERA_LATENCY_THRESHOLD_MS="$AI_CAMERA_LATENCY_THRESHOLD_MS" \
  AI_CAMERA_LATENCY_WINDOW_SAMPLES="$AI_CAMERA_LATENCY_WINDOW_SAMPLES" \
  PYTHONNOUSERSITE=1 \
  "$PY" scripts/common/install_systemd_units.py --role node1

sudo systemctl daemon-reload
sudo systemctl enable node1-ai-camera-api.service node1-ai-camera-receiver.service
sudo systemctl restart node1-ai-camera-api.service node1-ai-camera-receiver.service

echo "=== Service status ==="
systemctl --no-pager --full status node1-ai-camera-api.service | sed -n '1,20p'
systemctl --no-pager --full status node1-ai-camera-receiver.service | sed -n '1,24p'

echo "=== Health checks ==="
wait_for_http   "Node1 API health"   "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}/health"   node1-ai-camera-api.service   json   30   1
wait_for_http   "Node1 receiver metrics"   "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_METRICS_PORT}/metrics"   node1-ai-camera-receiver.service   raw   30   1
wait_for_http   "Node2 control agent health"   "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/health"   -   json   30   1

echo "=== Verify systemd command paths ==="
systemctl --no-pager --full status node1-ai-camera-api.service node1-ai-camera-receiver.service | grep -F "$REPO_ROOT" >/dev/null
systemctl cat node1-ai-camera-receiver.service | grep -F -- "--no-exit-on-no-frames" >/dev/null

echo "[OK] Node1 services are running from the current repo and receiver is persistent."

if [[ "$RUN_VALIDATIONS" -eq 1 ]]; then
  echo "=== Run Node1 validations through Step 12 ==="
  ./scripts/validate_step9_streaming.sh
  ./scripts/validate_step11_latency_monitoring.sh
  ./scripts/validate_step12_e2e_latency.sh
  ./scripts/validate_step12_yolo_onnx.sh
fi

echo "[OK] Node1 Step 12 startup complete. Log: $LOG_FILE"
