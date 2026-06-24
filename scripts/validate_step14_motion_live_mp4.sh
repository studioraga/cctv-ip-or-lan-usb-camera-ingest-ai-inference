#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f deploy/ai-camera.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source deploy/ai-camera.env
  set +a
fi
# shellcheck disable=SC1091
source scripts/lib/runtime_env.sh

OUT_DIR="${OUT_DIR:-results/step14}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/validate_step14_motion_live_mp4_$(date +%Y%m%d_%H%M%S).txt"
TMP_JSON="$OUT_DIR/motion_stream_start.json"
DL_MP4="$OUT_DIR/motion_live_download.mp4"

NODE1="http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT:-8080}"
NODE2="http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT:-8082}"
DURATION="${AI_CAMERA_STEP14_TEST_DURATION_SEC:-${AI_CAMERA_MOTION_STREAM_DURATION_SEC:-60}}"
PROFILE="${AI_CAMERA_PROFILE:-mjpeg_720p30}"
DEVICE="${AI_CAMERA_DEVICE:-/dev/video0}"
CAMERA_ID="${AI_CAMERA_CAMERA_ID:-c922_node2_gate}"

echo "=== Step 14 motion-triggered live MP4 validation ===" | tee "$OUT"
echo "Node1=$NODE1 Node2=$NODE2 duration=${DURATION}s profile=$PROFILE device=$DEVICE" | tee -a "$OUT"
echo "Output=$OUT" | tee -a "$OUT"

section(){ echo "" | tee -a "$OUT"; echo "=== $* ===" | tee -a "$OUT"; }
run(){ echo "+ $*" | tee -a "$OUT"; "$@" 2>&1 | tee -a "$OUT"; }

section "Health"
run curl -fsS "$NODE1/health"
run curl -fsS "$NODE2/health"

section "Trigger Node2-style motion event on Node1 API"
cat > "$TMP_JSON" <<JSON
{
  "camera_id": "$CAMERA_ID",
  "profile": "$PROFILE",
  "duration_sec": $DURATION,
  "device": "$DEVICE",
  "motion_score": 1.0,
  "motion_source": "node2_validation",
  "requested_by": "step14_validation",
  "notes": "Step 14 validation: Node2 motion event starts live fragmented-MP4 stream"
}
JSON
START_RESPONSE="$OUT_DIR/motion_stream_response.json"
run curl -fsS -X POST "$NODE1/motion/events/node2" -H 'Content-Type: application/json' -d @"$TMP_JSON" -o "$START_RESPONSE"
cat "$START_RESPONSE" | python3 -m json.tool | tee -a "$OUT"

SESSION_ID="$(python3 - <<PY
import json
print(json.load(open('$START_RESPONSE'))['session_id'])
PY
)"
LIVE_URL="$NODE1/motion/streams/$SESSION_ID/live.mp4"
PREVIEW_URL="$NODE1/motion/streams/$SESSION_ID/preview.mp4"
echo "session_id=$SESSION_ID" | tee -a "$OUT"
echo "live_mp4_url=$LIVE_URL" | tee -a "$OUT"
echo "preview_mp4_url=$PREVIEW_URL" | tee -a "$OUT"

section "Check current motion stream state"
run curl -fsS "$NODE1/motion/streams/current?camera_id=$CAMERA_ID"

section "Poll motion stream until completed"
DEADLINE=$((SECONDS + DURATION + 45))
STATUS="unknown"
while [[ $SECONDS -lt $DEADLINE ]]; do
  DETAIL="$OUT_DIR/session_${SESSION_ID}.json"
  curl -fsS "$NODE1/capture/sessions/$SESSION_ID" -o "$DETAIL"
  STATUS="$(python3 - <<PY
import json
print(json.load(open('$DETAIL'))['status'])
PY
)"
  FRAMES="$(python3 - <<PY
import json
print(json.load(open('$DETAIL')).get('frames_written', 0))
PY
)"
  echo "status=$STATUS frames=$FRAMES" | tee -a "$OUT"
  [[ "$STATUS" != "pending" && "$STATUS" != "running" ]] && break
  sleep 2
done
if [[ "$STATUS" != "completed" ]]; then
  echo "[FAIL] expected completed status, got $STATUS" | tee -a "$OUT"
  exit 1
fi

section "Verify artifacts"
ARTIFACTS="$OUT_DIR/artifacts_${SESSION_ID}.json"
run curl -fsS "$NODE1/capture/sessions/$SESSION_ID/artifacts" -o "$ARTIFACTS"
cat "$ARTIFACTS" | python3 -m json.tool | tee -a "$OUT"
python3 - <<PY | tee -a "$OUT"
import json, sys
items=json.load(open('$ARTIFACTS'))
types={x['artifact_type']: x for x in items}
missing=[x for x in ['live_mp4','preview_mp4','manifest','frames_jsonl','metrics_summary','report'] if x not in types]
if missing:
    print('[FAIL] missing artifacts:', ','.join(missing))
    sys.exit(1)
print('[OK] required Step 14 artifacts present')
print('live_mp4_size_bytes=', types['live_mp4'].get('size_bytes'))
print('preview_mp4_size_bytes=', types['preview_mp4'].get('size_bytes'))
PY

section "Download completed live MP4 through Node1 API"
run curl -fsS "$LIVE_URL" -o "$DL_MP4"
ls -lh "$DL_MP4" | tee -a "$OUT"
if [[ ! -s "$DL_MP4" ]]; then
  echo "[FAIL] downloaded live MP4 is empty" | tee -a "$OUT"
  exit 1
fi

section "Viewer commands"
cat <<EOF | tee -a "$OUT"
LAN client can view after/during a motion stream with:
  vlc $LIVE_URL

After completion, the preview MP4 is:
  vlc $PREVIEW_URL
EOF

echo "[OK] Step 14 motion-triggered live MP4 validation completed" | tee -a "$OUT"
echo "output=$OUT" | tee -a "$OUT"
