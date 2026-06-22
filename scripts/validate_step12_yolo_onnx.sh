#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
# Force this checkout even if deploy/ai-camera.env contains an old absolute path.
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"

PY="${PYTHON_BIN:-${REPO_ROOT}/${AI_CAMERA_VENV_DIR:-.venv}/bin/python}"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
MODEL_PATH="${AI_CAMERA_YOLO_MODEL:-}"
if [[ -n "$MODEL_PATH" && "$MODEL_PATH" != /* ]]; then
  MODEL_PATH="$REPO_ROOT/$MODEL_PATH"
fi

mkdir -p results/step12
OUT="results/step12/validate_step12_yolo_onnx_$(date +%Y%m%d_%H%M%S).txt"
log(){ echo "$*" | tee -a "$OUT"; }

log "=== Step 12 YOLO ONNX postprocess validation ==="
log "Output=${OUT}"
log "Configured AI_CAMERA_YOLO_MODEL=${MODEL_PATH:-<unset>}"

if ! "$PY" - <<'PY' >/dev/null 2>&1
import numpy  # noqa: F401
import cv2  # noqa: F401
PY
then
  log "[SKIP] YOLO validation requires numpy and OpenCV. This is expected on Node2 because Node2 does not install Node1 inference dependencies."
  log "[SKIP] Run this validation on Node1, or install the optional inference stack on this node."
  exit 0
fi

log "=== Unit tests ==="
"$PY" -m pytest -q tests/unit/test_yolo_onnx.py | tee -a "$OUT"

if [[ -n "$MODEL_PATH" && -s "$MODEL_PATH" ]]; then
  log "=== Optional real ONNX model smoke ==="
  "$PY" - <<PY | tee -a "$OUT"
import numpy as np
from services.node1_inference_worker.detectors.yolo_onnx import YoloOnnxDetector
model = YoloOnnxDetector('${MODEL_PATH}')
frame = np.zeros((480, 640, 3), dtype=np.uint8)
dets = model.detect(frame)
print('model=${MODEL_PATH}')
print('detections', len(dets))
print('first_detection', dets[0] if dets else None)
PY
elif [[ -n "$MODEL_PATH" ]]; then
  log "AI_CAMERA_YOLO_MODEL is configured but the file is missing: $MODEL_PATH"
  log "Run: ./scripts/models/download_yolo_onnx.sh"
  log "Unit postprocess validation is complete; real model smoke was skipped."
else
  log "AI_CAMERA_YOLO_MODEL not set; skipped real model smoke. Unit postprocess validation is complete."
fi
log "[OK] Step 12 YOLO ONNX validation completed"
