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
SAMPLES="${SAMPLES:-8}"
SLEEP_SEC="${SLEEP_SEC:-2}"

mkdir -p results/step11
OUT="results/step11/validate_step11_latency_monitoring_$(date +%Y%m%d_%H%M%S).txt"

log(){ echo "$*" | tee -a "$OUT"; }
json(){ python3 -m json.tool | tee -a "$OUT"; }

cleanup(){
  curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/stop" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "=== Step 11 bounded-slices latency monitoring validation ==="
log "Node1=${AI_CAMERA_NODE1_IP}:${NODE1_API_PORT}, metrics=${METRICS_PORT}, RTP=${RTP_PORT}"
log "Node2=${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}, camera=${CAMERA_ID}, device=${DEVICE}, profile=${PROFILE}"

log "=== Health ==="
curl -fsS "http://${AI_CAMERA_NODE1_IP}:${NODE1_API_PORT}/health" | json
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/health" | json

log "=== Start stream through Node2 API ==="
curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/start" \
  -H 'Content-Type: application/json' \
  -d "{\"camera_id\":\"${CAMERA_ID}\",\"node1_ip\":\"${AI_CAMERA_NODE1_IP}\",\"port\":${RTP_PORT},\"device\":\"${DEVICE}\",\"profile\":\"${PROFILE}\"}" | json
sleep 3

log "=== Node1 bounded-slices latency metrics samples ==="
frames_first=""
frames_last=""
latency_seen="0"
for i in $(seq 1 "$SAMPLES"); do
  log "--- sample $i ---"
  metrics="$(curl -fsS "http://${AI_CAMERA_NODE1_IP}:${METRICS_PORT}/metrics")"
  echo "$metrics" | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total|ai_camera_decode_failures_total|ai_camera_frame_gap_ms|ai_camera_capture_read_ms|ai_camera_capture_queue_wait_ms|ai_camera_latency_window_samples|ai_camera_latency_window_variation_ms|ai_camera_latency_bounded_slice_count|ai_camera_latency_longest_stable_window|ai_camera_latency_window_violation' -A 2 | tee -a "$OUT" || true
  value="$(echo "$metrics" | awk '/^ai_camera_frames_total\{/ {print $2; exit}')"
  [ -z "$frames_first" ] && frames_first="$value"
  frames_last="$value"
  if echo "$metrics" | grep -q '^ai_camera_latency_bounded_slice_count'; then
    latency_seen="1"
  fi
  sleep "$SLEEP_SEC"
done

log "frames_first=${frames_first:-missing} frames_last=${frames_last:-missing} latency_seen=${latency_seen}"
python3 - <<PY | tee -a "$OUT"
frames_first = float('${frames_first:-0}' or 0)
frames_last = float('${frames_last:-0}' or 0)
latency_seen = int('${latency_seen:-0}' or 0)
if frames_last <= frames_first:
    raise SystemExit('[FAIL] frames_total did not increase')
if latency_seen != 1:
    raise SystemExit('[FAIL] bounded-slices latency metrics were not exported')
print('[OK] frames_total increased and bounded-slices latency metrics were exported')
PY

log "=== Stop stream ==="
curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/stop" | json
trap - EXIT
log "[OK] Step 11 latency monitoring validation completed. Output: $OUT"
