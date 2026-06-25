#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/validate_step15_node2_motion_trigger.sh [--static-only] [--synthetic-trigger] [--no-wait]

Validates Step 15 Option A code paths:
  --static-only        import/build/decoder checks only; does not contact Node1/Node2
  --synthetic-trigger  post a synthetic person detection to Node1 /motion/events/node2
  --no-wait           when synthetic-trigger is used, do not wait for session completion

Run --static-only first on any machine. Run --synthetic-trigger on Node2 after
Node1 and Node2 services are started and the C922 is available for streaming.
USAGE
}

STATIC_ONLY=0
SYNTHETIC_TRIGGER=0
NO_WAIT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --static-only) STATIC_ONLY=1 ;;
    --synthetic-trigger) SYNTHETIC_TRIGGER=1 ;;
    --no-wait) NO_WAIT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
mkdir -p results/step15
LOG_FILE="results/step15/validate_step15_node2_motion_trigger_$(date +%Y%m%d_%H%M%S).txt"
exec > >(tee -a "$LOG_FILE") 2>&1

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="${AI_CAMERA_ENV_FILE:-$REPO_ROOT/deploy/ai-camera.env}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export PYTHONNOUSERSITE=1
PY="$(ai_camera_python)"
if [[ ! -x "$PY" ]]; then
  PY="${PYTHON_BIN:-python3}"
fi

echo "=== Step 15 Node2 motion trigger validation ==="
echo "repo=$REPO_ROOT"
echo "log=$LOG_FILE"
echo "python=$PY"

echo "=== Static imports and payload construction ==="
"$PY" - <<'PY'
from services.node2_motion_watcher.watcher import WatcherConfig, build_motion_event_payload, synthetic_detection, DetectionDebouncer, parse_args, config_from_args
cfg = WatcherConfig.from_env()
payload = build_motion_event_payload(cfg, motion_score=18.0, detections=synthetic_detection(), trigger_frame_id=7)
print('node1_url=', cfg.node1_url)
print('payload keys=', sorted(payload))
assert payload['event_type'] == 'motion_detected'
assert payload['detections'][0]['label'] == 'person'
d = DetectionDebouncer(window=5, required=2)
assert not d.update([])
assert not d.update([payload['detections'][0]])
assert d.update([payload['detections'][0]])
args = parse_args(['--yolo-confidence', '0.25', '--required-confirmations', '1', '--candidate-window', '3', '--synthetic-trigger'])
tuned = config_from_args(args)
assert tuned.yolo_confidence_threshold == 0.25
assert tuned.required_confirmations == 1
assert tuned.candidate_window == 3
print('debouncer and CLI tuning OK')
PY

echo "=== YOLOv8/YOLO11 decoder regression test ==="
"$PY" - <<'PY'
import pytest
np = pytest.importorskip('numpy')
from services.node1_inference_worker.detectors.yolo_onnx import LetterboxMeta, decode_yolo_output
meta = LetterboxMeta(original_shape=(640, 640), input_shape=(640, 640), ratio=1.0, pad_left=0.0, pad_top=0.0)
pred = np.zeros((1, 84, 1), dtype=np.float32)
pred[0, 0:4, 0] = [320, 320, 100, 100]
pred[0, 4, 0] = 0.95
class_names = ['person'] + [f'class_{i}' for i in range(1, 80)]
dets = decode_yolo_output([pred], meta, class_names=class_names, confidence_threshold=0.25, iou_threshold=0.45)
assert len(dets) == 1 and dets[0].label == 'person' and dets[0].class_id == 0
print('YOLOv8/YOLO11 COCO person class-0 decode OK')
PY

echo "=== Synthetic payload dry run ==="
"$PY" -m agents.node2.node2_motion_watcher --synthetic-trigger --dry-run --no-require-yolo --yolo-confidence 0.25 --required-confirmations 1 --candidate-window 3 | python3 -m json.tool

echo "=== Helper script syntax checks ==="
bash -n scripts/node2/test_c922_yolo_frame.sh scripts/node1/watch_motion_live_mp4_vlc.sh scripts/node2/run_node2_motion_watcher.sh scripts/lib/runtime_env.sh

if [[ "$STATIC_ONLY" -eq 1 ]]; then
  echo "[OK] Step 15 static validation PASS. Log: $LOG_FILE"
  exit 0
fi

if [[ -z "${AI_CAMERA_NODE1_IP:-}" ]]; then
  echo "ERROR: AI_CAMERA_NODE1_IP is required for network validation." >&2
  exit 1
fi
if [[ -z "${AI_CAMERA_NODE2_IP:-}" ]]; then
  AI_CAMERA_NODE2_IP="$(ai_camera_primary_ipv4 || true)"
  export AI_CAMERA_NODE2_IP
fi

echo "=== Node1 health ==="
curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}/health" | python3 -m json.tool

echo "=== Node2 health ==="
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/health" | python3 -m json.tool

echo "=== Node1 current motion stream before trigger ==="
curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}/motion/streams/current?camera_id=${AI_CAMERA_CAMERA_ID}" | python3 -m json.tool

if [[ "$SYNTHETIC_TRIGGER" -eq 1 ]]; then
  echo "=== Post synthetic Node2 person detection to Node1 ==="
  ARGS=(--synthetic-trigger --no-require-yolo)
  if [[ "$NO_WAIT" -eq 1 ]]; then ARGS+=(--no-wait); fi
  "/usr/bin/env" AI_CAMERA_NODE1_URL="http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}" "$PY" -m agents.node2.node2_motion_watcher "${ARGS[@]}"

  echo "=== Node1 current motion stream after trigger ==="
  curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}/motion/streams/current?camera_id=${AI_CAMERA_CAMERA_ID}" | python3 -m json.tool || true
else
  echo "[INFO] Network health checks completed. Add --synthetic-trigger to start a real Node1-managed capture session."
fi

echo "[OK] Step 15 validation PASS. Log: $LOG_FILE"
