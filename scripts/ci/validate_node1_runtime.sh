#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[CI:NODE1] OpenCV/GStreamer visibility"
python3 - <<'PY'
import cv2
print('cv2:', cv2.__version__)
info = cv2.getBuildInformation()
for line in info.splitlines():
    if 'GStreamer' in line:
        print(line)
        break
else:
    raise SystemExit('GStreamer line not found in OpenCV build info')
PY

echo "[CI:NODE1] ONNX Runtime import if installed"
python3 - <<'PY'
try:
    import onnxruntime as ort
    print('onnxruntime:', ort.__version__)
    print('providers:', ort.get_available_providers())
except ImportError:
    print('onnxruntime not installed; skipping optional import')
PY

echo "[CI:NODE1] SQLite schema smoke"
TMP_DB="/tmp/ai_camera_ci_$$.db"
python3 - <<PY
from services.common.event_db import EventDB
p = '$TMP_DB'
db = EventDB(p)
db.upsert_camera('ci_camera','CI Camera','usb_rtp','127.0.0.1','ci',True)
print(db.list_cameras())
PY
rm -f "$TMP_DB"

echo "[CI:NODE1] API module import"
python3 - <<'PY'
import services.node1_api_gateway.app as app
print('Node1 API app import OK:', app.app.title)
PY

echo "[CI:NODE1] Runtime validation PASS"
