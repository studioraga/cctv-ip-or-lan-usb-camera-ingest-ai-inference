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

grafana_sync_admin_password() {
  local password="${GRAFANA_ADMIN_PASSWORD:-}"
  if [[ "${AI_CAMERA_GRAFANA_SYNC_ADMIN_PASSWORD:-1}" != "1" ]]; then
    echo "[INFO] Grafana admin password sync disabled by AI_CAMERA_GRAFANA_SYNC_ADMIN_PASSWORD=0"
    return 0
  fi
  if [[ -z "$password" ]]; then
    echo "[WARN] GRAFANA_ADMIN_PASSWORD is empty; skipping Grafana admin password sync."
    return 0
  fi

  echo "=== Sync Grafana admin password from deploy env ==="
  # Grafana only applies GF_SECURITY_ADMIN_PASSWORD when the database is first
  # initialized. If the grafana_storage Docker volume already exists, changing
  # deploy/ai-camera.env does not update the stored admin password. Reset it so
  # the script's authenticated API checks use the same password as the operator
  # expects for browser login.
  if docker compose -f docker/docker-compose.node1.yml exec -T grafana \
      grafana cli admin reset-admin-password "$password" >/tmp/ai_camera_grafana_reset.$$ 2>/tmp/ai_camera_grafana_reset_err.$$; then
    sed 's/^/[GRAFANA] /' /tmp/ai_camera_grafana_reset.$$ || true
    rm -f /tmp/ai_camera_grafana_reset.$$ /tmp/ai_camera_grafana_reset_err.$$
    echo "[OK] Grafana admin password matches GRAFANA_ADMIN_PASSWORD from deploy env."
    return 0
  fi

  echo "[WARN] Grafana admin password sync failed; API checks may return 401 if the Docker volume has an older password."
  sed 's/^/[GRAFANA-RESET-ERR] /' /tmp/ai_camera_grafana_reset_err.$$ || true
  rm -f /tmp/ai_camera_grafana_reset.$$ /tmp/ai_camera_grafana_reset_err.$$
  return 0
}

grafana_search_dashboard() {
  local url="http://${AI_CAMERA_OBSERVABILITY_HEALTH_HOST}:3000/api/search?query=AI%20Camera"
  local user="${GRAFANA_ADMIN_USER:-admin}"
  local password="${GRAFANA_ADMIN_PASSWORD:-admin}"
  local body="/tmp/ai_camera_grafana_search.$$"
  local err="/tmp/ai_camera_grafana_search_err.$$"
  local code

  code="$(curl -sS -u "${user}:${password}" -o "$body" -w '%{http_code}' "$url" 2>"$err" || true)"
  case "$code" in
    200)
      python3 -m json.tool < "$body" || cat "$body"
      rm -f "$body" "$err"
      echo "[OK] Grafana authenticated API reachable and dashboard search completed."
      return 0
      ;;
    401|403)
      echo "[WARN] Grafana dashboard search returned HTTP ${code}."
      echo "[WARN] This usually means the existing grafana_storage Docker volume has a different admin password than GRAFANA_ADMIN_PASSWORD."
      echo "[WARN] The stack is healthy; browser login should use GRAFANA_ADMIN_USER=${user} and the current Grafana admin password."
      echo "[WARN] To force the password from deploy/ai-camera.env, keep AI_CAMERA_GRAFANA_SYNC_ADMIN_PASSWORD=1 and rerun this startup script, or reset manually:"
      echo "       docker compose -f docker/docker-compose.node1.yml exec -T grafana grafana cli admin reset-admin-password '<new-password>'"
      rm -f "$body" "$err"
      return 1
      ;;
    *)
      echo "[WARN] Grafana dashboard search failed with HTTP ${code:-curl-error}."
      sed 's/^/[GRAFANA-SEARCH-ERR] /' "$err" || true
      [[ -s "$body" ]] && sed 's/^/[GRAFANA-SEARCH-BODY] /' "$body" || true
      rm -f "$body" "$err"
      return 1
      ;;
  esac
}


echo "=== Node1 Step 13 startup ==="
echo "repo=$REPO_ROOT"
echo "log=$LOG_FILE"
echo "NODE1=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT} metrics=${AI_CAMERA_NODE1_METRICS_PORT}"
echo "NODE2=${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}"
echo "OBSERVABILITY_BIND=${AI_CAMERA_OBSERVABILITY_BIND:-127.0.0.1}"

case "${AI_CAMERA_OBSERVABILITY_BIND:-127.0.0.1}" in
  127.0.0.1|localhost) AI_CAMERA_OBSERVABILITY_HEALTH_HOST="127.0.0.1" ;;
  0.0.0.0|::) AI_CAMERA_OBSERVABILITY_HEALTH_HOST="${AI_CAMERA_NODE1_IP}" ;;
  *) AI_CAMERA_OBSERVABILITY_HEALTH_HOST="${AI_CAMERA_OBSERVABILITY_BIND}" ;;
esac
export AI_CAMERA_OBSERVABILITY_HEALTH_HOST

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
wait_http "Prometheus" "http://${AI_CAMERA_OBSERVABILITY_HEALTH_HOST}:9090/-/healthy" 45 1
wait_http "Grafana" "http://${AI_CAMERA_OBSERVABILITY_HEALTH_HOST}:3000/api/health" 45 1
curl -fsS "http://${AI_CAMERA_OBSERVABILITY_HEALTH_HOST}:3000/api/health" | python3 -m json.tool || true

grafana_sync_admin_password
grafana_search_dashboard || true

if [[ "$RUN_CAPTURE_TEST" -eq 1 ]]; then
  echo "=== Run Step 13 capture-session validation ==="
  ./scripts/validate_step13_capture_session.sh
else
  echo "[INFO] Capture-session validation skipped. Re-run with --capture-test to validate dataset capture."
fi

echo "[INFO] Local health URL: http://${AI_CAMERA_OBSERVABILITY_HEALTH_HOST}:3000/api/health"
if [[ "${AI_CAMERA_OBSERVABILITY_BIND:-127.0.0.1}" == "127.0.0.1" || "${AI_CAMERA_OBSERVABILITY_BIND:-127.0.0.1}" == "localhost" ]]; then
  echo "[INFO] Grafana is bound to localhost for lab-safe hardening. Set AI_CAMERA_OBSERVABILITY_BIND=0.0.0.0 or ${AI_CAMERA_NODE1_IP} for LAN dashboard access."
else
  echo "[INFO] Grafana dashboard URL: http://${AI_CAMERA_NODE1_IP}:3000/d/ai-camera-capture-session-demo/ai-camera-capture-session-demo"
fi
echo "[OK] Node1 Step 13 startup complete. Log: $LOG_FILE"
