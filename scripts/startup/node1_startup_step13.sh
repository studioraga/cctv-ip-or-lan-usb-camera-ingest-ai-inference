#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/startup/node1_startup_step13.sh [--capture-test]

Starts and validates the Node1 Step 13 observability/capture demo:
  - repairs stale configs/runtime/prometheus.yml directory if Docker created one
  - renders configs/runtime/prometheus.yml from docker/prometheus.yml
  - validates Grafana/Prometheus provisioning files
  - starts Prometheus, Grafana, and Qdrant with Docker Compose
  - waits for Prometheus and Grafana health endpoints
  - optionally runs the capture-session dataset validation

Options:
  --capture-test  run scripts/validate_step13_capture_session.sh after stack health
  -h, --help      show this help
USAGE
}

RUN_CAPTURE_TEST=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --capture-test) RUN_CAPTURE_TEST=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

mkdir -p results/startup
LOG_FILE="results/startup/node1_startup_step13_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="$REPO_ROOT/deploy/ai-camera.env"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"

wait_http() {
  local name="$1" url="$2" attempts="${3:-30}" delay="${4:-1}"
  echo "=== Wait for ${name}: ${url} ==="
  for i in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/tmp/ai_camera_step13_health.$$ 2>/tmp/ai_camera_step13_health_err.$$; then
      cat /tmp/ai_camera_step13_health.$$
      rm -f /tmp/ai_camera_step13_health.$$ /tmp/ai_camera_step13_health_err.$$
      echo "[OK] ${name} is reachable."
      return 0
    fi
    echo "[WAIT] ${name} not ready yet (${i}/${attempts})"
    sleep "$delay"
  done
  echo "[FAIL] ${name} did not become ready: ${url}" >&2
  cat /tmp/ai_camera_step13_health_err.$$ >&2 || true
  rm -f /tmp/ai_camera_step13_health.$$ /tmp/ai_camera_step13_health_err.$$
  return 1
}

echo "=== Node1 Step 13 startup ==="
echo "repo=$REPO_ROOT"
echo "log=$LOG_FILE"
echo "NODE1=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT} metrics=${AI_CAMERA_NODE1_METRICS_PORT}"
echo "NODE2=${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[FAIL] docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[FAIL] Docker Compose v2 plugin is not available: docker compose version failed." >&2
  exit 1
fi

echo "=== Render Prometheus config ==="
./scripts/common/render_prometheus_config.sh

if [[ ! -f configs/runtime/prometheus.yml ]]; then
  echo "[FAIL] configs/runtime/prometheus.yml is not a regular file after render." >&2
  ls -ld configs/runtime configs/runtime/prometheus.yml >&2 || true
  exit 1
fi

echo "=== Validate Step 13 provisioning ==="
./scripts/validate_step13_grafana_stack.sh

echo "=== Start Docker stack ==="
docker compose -f docker/docker-compose.node1.yml up -d

echo "=== Compose status ==="
docker compose -f docker/docker-compose.node1.yml ps

echo "=== Health checks ==="
wait_http "Prometheus" "http://${AI_CAMERA_NODE1_IP}:9090/-/healthy" 45 1
wait_http "Grafana" "http://${AI_CAMERA_NODE1_IP}:3000/api/health" 45 1
curl -fsS "http://${AI_CAMERA_NODE1_IP}:3000/api/health" | python3 -m json.tool || true

if curl -fsS -u "${GRAFANA_ADMIN_USER:-admin}:${GRAFANA_ADMIN_PASSWORD:-admin}" "http://${AI_CAMERA_NODE1_IP}:3000/api/search?query=AI%20Camera" | python3 -m json.tool; then
  echo "[OK] Grafana API reachable."
else
  echo "[WARN] Grafana dashboard search failed; check provisioning logs if the dashboard is missing."
fi

if [[ "$RUN_CAPTURE_TEST" -eq 1 ]]; then
  echo "=== Run Step 13 capture-session validation ==="
  ./scripts/validate_step13_capture_session.sh
else
  echo "[INFO] Capture-session validation skipped. Re-run with --capture-test to validate dataset capture."
fi

echo "[OK] Node1 Step 13 startup complete. Log: $LOG_FILE"
