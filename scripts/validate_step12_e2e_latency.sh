#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source scripts/lib/runtime_env.sh

: "${AI_CAMERA_NODE1_IP:?AI_CAMERA_NODE1_IP required}"
: "${AI_CAMERA_NODE2_IP:?AI_CAMERA_NODE2_IP required}"
NODE1_API_PORT="${AI_CAMERA_NODE1_API_PORT:-8080}"
NODE2_API_PORT="${AI_CAMERA_NODE2_API_PORT:-8082}"
RTP_PORT="${AI_CAMERA_NODE1_RTP_PORT:-5000}"
METRICS_PORT="${AI_CAMERA_NODE1_METRICS_PORT:-9101}"
PROFILE="${AI_CAMERA_PROFILE:-mjpeg_720p30}"
DEVICE="${AI_CAMERA_DEVICE:-/dev/video0}"
CAMERA_ID="${AI_CAMERA_CAMERA_ID:-c922_node2_gate}"
PY="${PYTHON_BIN:-${REPO_ROOT}/${AI_CAMERA_VENV_DIR:-.venv}/bin/python}"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
SAMPLES="${SAMPLES:-10}"
SLEEP_SEC="${SLEEP_SEC:-2}"
TRANSPORT="timed_jpeg_udp"

mkdir -p results/step12
OUT="results/step12/validate_step12_e2e_latency_$(date +%Y%m%d_%H%M%S).txt"
RECEIVER_LOG="results/step12/node1_timed_jpeg_receiver_$(date +%Y%m%d_%H%M%S).log"
EVENT_LOG="results/step12/e2e_events.jsonl"
RECEIVER_PID=""
RECEIVER_WAS_ACTIVE="0"

log(){ echo "$*" | tee -a "$OUT"; }
json(){ python3 -m json.tool | tee -a "$OUT"; }

cleanup(){
  curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/stop" >/dev/null 2>&1 || true
  if [ -n "$RECEIVER_PID" ] && kill -0 "$RECEIVER_PID" >/dev/null 2>&1; then
    kill -INT "$RECEIVER_PID" >/dev/null 2>&1 || true
    wait "$RECEIVER_PID" >/dev/null 2>&1 || true
  fi
  if [ "$RECEIVER_WAS_ACTIVE" = "1" ]; then
    sudo systemctl restart node1-ai-camera-receiver.service >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

log "=== Step 12 true E2E timestamped JPEG/UDP validation ==="
log "Node1=${AI_CAMERA_NODE1_IP}:${NODE1_API_PORT}, metrics=${METRICS_PORT}, UDP=${RTP_PORT}"
log "Node2=${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}, camera=${CAMERA_ID}, device=${DEVICE}, profile=${PROFILE}, transport=${TRANSPORT}"
log "Output=${OUT}"

if systemctl is-active --quiet node1-ai-camera-receiver.service; then
  RECEIVER_WAS_ACTIVE="1"
  log "=== Stop production Node1 receiver temporarily so validation can bind UDP ${RTP_PORT} and metrics ${METRICS_PORT} ==="
  sudo systemctl stop node1-ai-camera-receiver.service
fi

log "=== Health ==="
curl -fsS "http://${AI_CAMERA_NODE1_IP}:${NODE1_API_PORT}/health" | json
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/health" | json

log "=== Start manual Node1 timestamped JPEG receiver ==="
"$PY" -m agents.node1.node1_receiver_agent \
  --transport "$TRANSPORT" \
  --profile "$PROFILE" \
  --port "$RTP_PORT" \
  --camera-id "$CAMERA_ID" \
  --event-log "$EVENT_LOG" \
  --metrics \
  --metrics-port "$METRICS_PORT" \
  --report-interval 1 \
  --startup-timeout-sec 30 \
  --no-frame-timeout-sec 10 \
  > "$RECEIVER_LOG" 2>&1 &
RECEIVER_PID=$!
log "manual_receiver_pid=${RECEIVER_PID} log=${RECEIVER_LOG}"
sleep 2

log "=== Start timestamped stream through Node2 API ==="
curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/start" \
  -H 'Content-Type: application/json' \
  -d "{\"camera_id\":\"${CAMERA_ID}\",\"node1_ip\":\"${AI_CAMERA_NODE1_IP}\",\"port\":${RTP_PORT},\"device\":\"${DEVICE}\",\"profile\":\"${PROFILE}\",\"transport\":\"${TRANSPORT}\"}" | json
sleep 3

log "=== E2E latency metrics samples ==="
frames_first=""
frames_last=""
e2e_seen="0"
for i in $(seq 1 "$SAMPLES"); do
  log "--- sample $i ---"
  metrics="$(curl -fsS "http://${AI_CAMERA_NODE1_IP}:${METRICS_PORT}/metrics")"
  echo "$metrics" | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total|ai_camera_e2e_latency_ms|ai_camera_e2e_frame_id|ai_camera_e2e_clock_delta_ms|ai_camera_latency_window_samples|ai_camera_latency_window_variation_ms|ai_camera_latency_bounded_slice_count|ai_camera_latency_window_violation' -A 2 | tee -a "$OUT" || true
  value="$(echo "$metrics" | awk '/^ai_camera_frames_total\{/ {print $2; exit}')"
  [ -z "$frames_first" ] && frames_first="$value"
  frames_last="$value"
  if echo "$metrics" | grep -q '^ai_camera_e2e_latency_ms_count'; then
    e2e_seen="1"
  fi
  sleep "$SLEEP_SEC"
done

log "frames_first=${frames_first:-missing} frames_last=${frames_last:-missing} e2e_seen=${e2e_seen}"
python3 - <<PY | tee -a "$OUT"
frames_first = float('${frames_first:-0}' or 0)
frames_last = float('${frames_last:-0}' or 0)
e2e_seen = int('${e2e_seen:-0}' or 0)
if frames_last <= frames_first:
    raise SystemExit('[FAIL] frames_total did not increase')
if e2e_seen != 1:
    raise SystemExit('[FAIL] E2E latency metrics were not exported')
print('[OK] frames_total increased and E2E timestamped latency metrics were exported')
PY

log "=== Stop stream ==="
curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/stop" | json
trap - EXIT
cleanup
log "[OK] Step 12 E2E timestamped latency validation completed. Output: $OUT"
