#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/startup/node2_startup_step15.sh [--install-deps] [--no-enable-watcher]

Bootstraps Node2 for Step 15 Option A:
  - verifies Node2 control agent readiness
  - installs the Node2 motion watcher systemd unit
  - optionally enables/restarts node2-motion-watcher.service
  - verifies the watcher can build a synthetic Node1 motion payload

Before running with the real watcher enabled:
  - set AI_CAMERA_NODE_ROLE=node2 in deploy/ai-camera.env
  - set AI_CAMERA_NODE1_IP=<Node1 LAN IP>
  - set AI_CAMERA_NODE2_IP=<Node2 LAN IP> if auto-detect is not enough
  - set AI_CAMERA_NODE2_WATCHER_YOLO_MODEL or AI_CAMERA_YOLO_MODEL to a local ONNX model
  - keep AI_CAMERA_NODE2_WATCHER_REQUIRE_YOLO=1 for product validation

Options:
  --install-deps       run scripts/node2/setup_node2_venv.sh first
  --no-enable-watcher  install but do not enable/restart the watcher service
  -h, --help           show this help
USAGE
}

INSTALL_DEPS=0
ENABLE_WATCHER=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-deps) INSTALL_DEPS=1 ;;
    --no-enable-watcher) ENABLE_WATCHER=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
mkdir -p results/startup
LOG_FILE="results/startup/node2_startup_step15_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Node2 Step 15 Option A startup ==="
echo "repo=$REPO_ROOT"
echo "log=$LOG_FILE"

ENV_FILE="$REPO_ROOT/deploy/ai-camera.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$REPO_ROOT/deploy/ai-camera.env.example" "$ENV_FILE"
  echo "[INFO] Created $ENV_FILE from example. Edit it before enabling the watcher."
fi

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="$ENV_FILE"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export PYTHONNOUSERSITE=1
export AI_CAMERA_NODE_ROLE="node2"

LOCAL_IP="$(ai_camera_primary_ipv4 || true)"
export AI_CAMERA_NODE2_IP="${AI_CAMERA_NODE2_IP:-$LOCAL_IP}"
if [[ -z "${AI_CAMERA_NODE2_IP:-}" ]]; then
  echo "ERROR: could not auto-detect Node2 IP. Set AI_CAMERA_NODE2_IP." >&2
  exit 1
fi
if [[ -z "${AI_CAMERA_NODE1_IP:-}" ]]; then
  echo "ERROR: AI_CAMERA_NODE1_IP is required on Node2." >&2
  exit 1
fi

echo "NODE2=${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT} camera=${AI_CAMERA_DEVICE} profile=${AI_CAMERA_PROFILE}"
echo "NODE1=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT} capture_udp=${AI_CAMERA_CAPTURE_UDP_PORT}"
echo "WATCHER sample_fps=${AI_CAMERA_NODE2_WATCHER_SAMPLE_FPS:-5} motion_threshold=${AI_CAMERA_NODE2_WATCHER_MOTION_THRESHOLD:-12} require_yolo=${AI_CAMERA_NODE2_WATCHER_REQUIRE_YOLO:-1}"

if [[ "$INSTALL_DEPS" -eq 1 || ! -x "$(ai_camera_python)" ]]; then
  echo "=== Install Node2 dependencies / setup venv ==="
  "$REPO_ROOT/scripts/node2/setup_node2_venv.sh"
fi

PY="$(ai_camera_python)"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtual environment python is missing: $PY" >&2
  exit 1
fi

echo "=== Prepare deployment ==="
./scripts/common/prepare_deployment.sh node2

echo "=== Install Node2 systemd units ==="
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
  "$PY" scripts/common/install_systemd_units.py --role node2

sudo systemctl daemon-reload
sudo systemctl enable node2-camera-control-agent.service
sudo systemctl restart node2-camera-control-agent.service

sleep 1
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/health" | python3 -m json.tool

echo "=== Watcher synthetic dry-run payload ==="
"$PY" -m agents.node2.node2_motion_watcher --synthetic-trigger --dry-run --no-require-yolo | python3 -m json.tool

if [[ "$ENABLE_WATCHER" -eq 1 ]]; then
  echo "=== Enable Node2 motion watcher service ==="
  sudo systemctl enable node2-motion-watcher.service
  sudo systemctl restart node2-motion-watcher.service
  systemctl --no-pager --full status node2-motion-watcher.service | sed -n '1,28p'
else
  echo "[INFO] Watcher unit installed but not enabled. Start manually with: sudo systemctl start node2-motion-watcher.service"
fi

echo "[OK] Node2 Step 15 startup complete. Log: $LOG_FILE"
