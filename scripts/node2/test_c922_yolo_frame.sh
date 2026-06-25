#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/node2/test_c922_yolo_frame.sh [--image PATH]

Captures one C922 frame from AI_CAMERA_DEVICE and runs the Step 15 shared YOLO
ONNX detector against that frame. Use this before the real watcher one-shot to
prove that yolo11n.onnx decodes a visible person/object correctly.

Environment knobs:
  AI_CAMERA_NODE2_WATCHER_YOLO_MODEL   default: AI_CAMERA_YOLO_MODEL
  AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE default: 0.25 recommended for smoke
  AI_CAMERA_NODE2_WATCHER_YOLO_IOU     default: 0.45
  AI_CAMERA_DEVICE                     default: /dev/video0
  AI_CAMERA_PROFILE                    default: mjpeg_720p30
  AI_CAMERA_NODE2_WATCHER_CLASSES      default: person,bicycle,car,...
USAGE
}

IMAGE="/tmp/c922_yolo_test.jpg"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
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

"$PY" - "$IMAGE" <<'PY'
import json
import os
import sys
from pathlib import Path

import cv2

from agents.node2.node2_streamer_controller import PROFILES
from services.node2_motion_watcher.watcher import COCO_CLASS_NAMES, DEFAULT_INTERESTING_LABELS, normalize_detection
from services.common.detectors.yolo_onnx import YoloOnnxDetector

image_path = Path(sys.argv[1])
repo = Path(os.environ.get("AI_CAMERA_REPO_ROOT", ".")).resolve()
device = os.environ.get("AI_CAMERA_DEVICE", "/dev/video0")
profile_name = os.environ.get("AI_CAMERA_PROFILE", "mjpeg_720p30")
profile = PROFILES.get(profile_name, {})
model = os.environ.get("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL") or os.environ.get("AI_CAMERA_YOLO_MODEL", "")
if not model:
    raise SystemExit("AI_CAMERA_NODE2_WATCHER_YOLO_MODEL or AI_CAMERA_YOLO_MODEL is required")
model_path = Path(model)
if not model_path.is_absolute():
    model_path = repo / model_path
if not model_path.is_file():
    raise SystemExit(f"YOLO model not found: {model_path}")

cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
if not cap.isOpened():
    raise SystemExit(f"unable to open camera device: {device}")
try:
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    if profile:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(profile.get("width", 1280)))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(profile.get("height", 720)))
        cap.set(cv2.CAP_PROP_FPS, float(profile.get("fps", 30)))
    frame = None
    for _ in range(8):
        ok, candidate = cap.read()
        if ok:
            frame = candidate
    if frame is None:
        raise SystemExit("camera opened but no frame could be read")
finally:
    cap.release()

image_path.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(image_path), frame)

confidence = float(os.environ.get("AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE", "0.25"))
iou = float(os.environ.get("AI_CAMERA_NODE2_WATCHER_YOLO_IOU", "0.45"))
input_size = int(os.environ.get("AI_CAMERA_NODE2_WATCHER_YOLO_INPUT_SIZE", "640"))
interesting = {x.strip().lower() for x in os.environ.get(
    "AI_CAMERA_NODE2_WATCHER_CLASSES",
    ",".join(DEFAULT_INTERESTING_LABELS),
).split(",") if x.strip()}

detector = YoloOnnxDetector(
    str(model_path),
    input_size=input_size,
    class_names=COCO_CLASS_NAMES,
    confidence_threshold=confidence,
    iou_threshold=iou,
)
raw = [normalize_detection(det) for det in detector.detect(frame)]
interesting_dets = [det for det in raw if det["label"].lower() in interesting]
print(json.dumps({
    "image": str(image_path),
    "device": device,
    "profile": profile_name,
    "model": str(model_path),
    "confidence_threshold": confidence,
    "iou_threshold": iou,
    "raw_detection_count": len(raw),
    "raw_detections": raw[:20],
    "interesting_labels": sorted(interesting),
    "interesting_detection_count": len(interesting_dets),
    "interesting_detections": interesting_dets[:20],
}, indent=2, sort_keys=True))
PY
