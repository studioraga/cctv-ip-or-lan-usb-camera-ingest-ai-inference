#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/startup/node2_startup_steps12.sh [--install-deps]

Bootstraps Node2 through the validated Step 12 milestone:
  - creates deploy/ai-camera.env if missing
  - sources current repo-local runtime env
  - optionally installs Node2 dependencies / recreates .venv
  - prepares runtime config, policy, and tests
  - installs, daemon-reloads, enables, and restarts Node2 systemd unit
  - checks Node2 service health and camera format availability

Required before first run:
  - edit deploy/ai-camera.env and set AI_CAMERA_NODE1_IP=<Node1 LAN IP>
  - set AI_CAMERA_NODE_ROLE=node2 on Node2

Options:
  --install-deps  run scripts/node2/install_node2_dependencies.sh first
  -h, --help      show this help
USAGE
}

INSTALL_DEPS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-deps) INSTALL_DEPS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

wait_for_json_health() {
  local label="$1"
  local url="$2"
  local service="$3"
  local attempts="${4:-30}"
  local delay="${5:-1}"
  local tmp_err
  tmp_err="$(mktemp)"

  echo "[WAIT] ${label}: ${url}"
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 2 "$url" 2>"$tmp_err" | python3 -m json.tool; then
      rm -f "$tmp_err"
      echo "[OK] ${label} is healthy"
      return 0
    fi

    if ! systemctl is-active --quiet "$service"; then
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
  echo "[INFO] Listening sockets on the expected port:"
  ss -lntp 2>/dev/null | grep -E ":${AI_CAMERA_NODE2_API_PORT}\b" || true
  echo "[INFO] ${service} status:"
  systemctl --no-pager --full status "$service" || true
  echo "[INFO] ${service} journal tail:"
  journalctl -u "$service" --no-pager -n 120 || true
  rm -f "$tmp_err"
  return 1
}

mkdir -p results/startup
LOG_FILE="results/startup/node2_startup_steps12_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Node2 Step 12 startup ==="
echo "repo=$REPO_ROOT"
echo "log=$LOG_FILE"

ENV_FILE="$REPO_ROOT/deploy/ai-camera.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$REPO_ROOT/deploy/ai-camera.env.example" "$ENV_FILE"
  echo "[INFO] Created $ENV_FILE from example. Edit it if Node1 IP is not already exported."
fi

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="$ENV_FILE"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
# Force this checkout even if deploy/ai-camera.env contains an old absolute path.
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export PYTHONNOUSERSITE=1
export AI_CAMERA_NODE_ROLE="node2"

LOCAL_IP="$(ai_camera_primary_ipv4 || true)"
export AI_CAMERA_NODE2_IP="${AI_CAMERA_NODE2_IP:-$LOCAL_IP}"
if [[ -z "${AI_CAMERA_NODE2_IP:-}" ]]; then
  echo "ERROR: could not auto-detect Node2 IP. Set AI_CAMERA_NODE2_IP in deploy/ai-camera.env." >&2
  exit 1
fi
if [[ -z "${AI_CAMERA_NODE1_IP:-}" ]]; then
  echo "ERROR: AI_CAMERA_NODE1_IP is required on Node2. Edit deploy/ai-camera.env and set Node1 LAN IP." >&2
  exit 1
fi

echo "NODE2=${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT} camera=${AI_CAMERA_DEVICE} profile=${AI_CAMERA_PROFILE}"
echo "NODE1=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT} rtp=${AI_CAMERA_NODE1_RTP_PORT} capture_udp=${AI_CAMERA_CAPTURE_UDP_PORT}"

if [[ "$INSTALL_DEPS" -eq 1 || ! -x "$(ai_camera_python)" ]]; then
  echo "=== Install Node2 dependencies / setup venv ==="
  "$REPO_ROOT/scripts/node2/install_node2_dependencies.sh"
fi

PY="$(ai_camera_python)"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtual environment python is missing: $PY" >&2
  exit 1
fi

if command -v v4l2-ctl >/dev/null 2>&1 && [[ -e "$AI_CAMERA_DEVICE" ]]; then
  echo "=== Camera capability check ==="
  v4l2-ctl --device="$AI_CAMERA_DEVICE" --list-formats-ext | grep -A8 -B2 '1280x720' || true
else
  echo "[WARN] Camera capability check skipped: v4l2-ctl missing or $AI_CAMERA_DEVICE not present."
fi

echo "=== Prepare deployment ==="
./scripts/common/prepare_deployment.sh node2

echo "=== Install Node2 systemd unit ==="
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

echo "=== Service status ==="
systemctl --no-pager --full status node2-camera-control-agent.service | sed -n '1,24p'

echo "=== Health check ==="
wait_for_json_health   "Node2 control agent health"   "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/health"   node2-camera-control-agent.service   30   1

echo "=== Verify systemd command path ==="
if systemctl cat node2-camera-control-agent.service | grep -F "$REPO_ROOT" >/dev/null; then
  echo "[OK] Node2 service unit points to the current repo."
else
  echo "[FAIL] Node2 service unit does not point to current repo: $REPO_ROOT" >&2
  systemctl cat node2-camera-control-agent.service >&2
  exit 1
fi

echo "[OK] Node2 Step 12 startup complete. Log: $LOG_FILE"
