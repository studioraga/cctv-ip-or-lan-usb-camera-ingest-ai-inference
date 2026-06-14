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
SAMPLES="${SAMPLES:-5}"

mkdir -p results/step9
OUT="results/step9/validate_step9_streaming_$(date +%Y%m%d_%H%M%S).txt"

log(){ echo "$*" | tee -a "$OUT"; }
json(){ python3 -m json.tool | tee -a "$OUT"; }

log "=== Step 9 streaming validation ==="
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

log "=== Node2 status ==="
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/status" | json

log "=== Node1 metrics samples ==="
first=""
last=""
for i in $(seq 1 "$SAMPLES"); do
  log "--- sample $i ---"
  metrics="$(curl -fsS "http://${AI_CAMERA_NODE1_IP}:${METRICS_PORT}/metrics")"
  echo "$metrics" | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total|ai_camera_decode_failures_total' -A 2 | tee -a "$OUT"
  value="$(echo "$metrics" | awk '/^ai_camera_frames_total\{/ {print $2; exit}')"
  [ -z "$first" ] && first="$value"
  last="$value"
  sleep 1
done

log "frames_first=${first:-missing} frames_last=${last:-missing}"
python3 - <<PY | tee -a "$OUT"
first = float('${first:-0}' or 0)
last = float('${last:-0}' or 0)
if last <= first:
    raise SystemExit('[FAIL] frames_total did not increase')
print('[OK] frames_total increased')
PY

log "=== Stop stream ==="
curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/stop" | json
sleep 1
log "=== Final status ==="
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${NODE2_API_PORT}/stream/status" | json
log "[OK] Step 9 streaming validation completed. Output: $OUT"
