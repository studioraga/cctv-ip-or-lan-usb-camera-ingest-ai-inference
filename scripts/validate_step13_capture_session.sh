#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source scripts/lib/runtime_env.sh

NODE1_API="http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}"
NODE2_API="http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}"
DURATION="${AI_CAMERA_CAPTURE_TEST_DURATION_SEC:-10}"
OUT_DIR="results/step13"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/validate_step13_capture_session_$(date +%Y%m%d_%H%M%S).txt"

log(){ echo "$*" | tee -a "$OUT"; }
json_pp(){ python3 -m json.tool 2>/dev/null || cat; }

log "=== Step 13 capture-session dataset validation ==="
log "Node1=${NODE1_API}, Node2=${NODE2_API}, capture_udp=${AI_CAMERA_CAPTURE_UDP_PORT}, duration=${DURATION}s"
log "Output=${OUT}"

log "=== Health ==="
curl -fsS "$NODE1_API/health" | tee -a "$OUT" | json_pp | tee -a "$OUT" >/dev/null
curl -fsS "$NODE2_API/health" | tee -a "$OUT" | json_pp | tee -a "$OUT" >/dev/null

log "=== Start capture session through Node1 API ==="
REQ=$(cat <<JSON
{
  "camera_id": "${AI_CAMERA_CAMERA_ID}",
  "profile": "${AI_CAMERA_PROFILE}",
  "duration_sec": ${DURATION},
  "device": "${AI_CAMERA_DEVICE}",
  "transport": "timed_jpeg_udp",
  "dataset_mode": "source_jpeg",
  "frame_stride": ${AI_CAMERA_CAPTURE_DEFAULT_FRAME_STRIDE:-1},
  "requested_by": "validate_step13_capture_session",
  "notes": "automated Step 13 validation"
}
JSON
)
START_JSON=$(curl -fsS -X POST "$NODE1_API/capture/sessions" -H 'Content-Type: application/json' -d "$REQ")
echo "$START_JSON" | tee -a "$OUT" | python3 -m json.tool | tee -a "$OUT" >/dev/null
SESSION_ID=$(python3 - <<PY
import json
print(json.loads('''$START_JSON''')['session_id'])
PY
)
log "session_id=${SESSION_ID}"

log "=== Poll capture session ==="
STATUS=""
for _ in $(seq 1 $((DURATION + 20))); do
  STATUS_JSON=$(curl -fsS "$NODE1_API/capture/sessions/${SESSION_ID}")
  STATUS=$(python3 - <<PY
import json
print(json.loads('''$STATUS_JSON''')['status'])
PY
)
  FRAMES=$(python3 - <<PY
import json
print(json.loads('''$STATUS_JSON''').get('frames_written', 0))
PY
)
  log "status=${STATUS} frames=${FRAMES}"
  [[ "$STATUS" =~ ^(completed|failed|cancelled)$ ]] && break
  sleep 1
done

if [[ "$STATUS" != "completed" ]]; then
  log "[FAIL] expected completed status, got ${STATUS}"
  curl -fsS -X POST "$NODE1_API/capture/sessions/${SESSION_ID}/stop" >/dev/null || true
  exit 1
fi

SESSION_JSON=$(curl -fsS "$NODE1_API/capture/sessions/${SESSION_ID}")
echo "$SESSION_JSON" | python3 -m json.tool | tee -a "$OUT" >/dev/null
DATASET_PATH=$(python3 - <<PY
import json
print(json.loads('''$SESSION_JSON''')['dataset_path'])
PY
)
FRAMES_WRITTEN=$(python3 - <<PY
import json
print(json.loads('''$SESSION_JSON''').get('frames_written', 0))
PY
)

log "=== Verify dataset artifacts ==="
[[ "$FRAMES_WRITTEN" -gt 0 ]] || { log "[FAIL] no frames were written"; exit 1; }
[[ -f "$DATASET_PATH/manifest.json" ]] || { log "[FAIL] missing manifest.json"; exit 1; }
[[ -f "$DATASET_PATH/metadata/frames.jsonl" ]] || { log "[FAIL] missing metadata/frames.jsonl"; exit 1; }
[[ -f "$DATASET_PATH/artifacts/metrics_summary.json" ]] || { log "[FAIL] missing metrics_summary.json"; exit 1; }
[[ -f "$DATASET_PATH/artifacts/report.md" ]] || { log "[FAIL] missing report.md"; exit 1; }
FRAME_COUNT=$(find "$DATASET_PATH/frames" -type f -name 'frame_*.jpg' | wc -l)
log "dataset_path=${DATASET_PATH} frames_written=${FRAMES_WRITTEN} files=${FRAME_COUNT}"
[[ "$FRAME_COUNT" -gt 0 ]] || { log "[FAIL] no frame_*.jpg files found"; exit 1; }

log "=== Verify capture metrics ==="
METRICS=$(curl -fsS "$NODE1_API/metrics")
echo "$METRICS" | grep -E 'ai_camera_capture_session_(active|frames_total|bytes_written_total|e2e_latency_ms)' | tee -a "$OUT" >/dev/null

log "=== Verify Node2 stopped ==="
curl -fsS "$NODE2_API/stream/status" | tee -a "$OUT" | python3 -m json.tool | tee -a "$OUT" >/dev/null
RUNNING=$(curl -fsS "$NODE2_API/stream/status" | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("running", False)).lower())')
[[ "$RUNNING" == "false" ]] || { log "[FAIL] Node2 stream still running"; exit 1; }

log "[OK] Step 13 capture-session dataset validation completed"
log "output=${OUT}"
