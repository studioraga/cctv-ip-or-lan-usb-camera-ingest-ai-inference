#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
PYTHON_BIN="${PYTHON_BIN:-python}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

echo "[CI:NODE1] OpenCV/GStreamer visibility"
"$PYTHON_BIN" - <<'PY'
import sys, cv2
print('python:', sys.executable)
print('cv2:', cv2.__version__)
line = next((x for x in cv2.getBuildInformation().splitlines() if 'GStreamer' in x), None)
print(line or 'GStreamer line not found')
if line is None or 'YES' not in line:
    raise SystemExit('Node1 OpenCV must report GStreamer: YES')
PY

echo "[CI:NODE1] ONNX Runtime import if installed"
"$PYTHON_BIN" - <<'PY'
try:
    import onnxruntime as ort
    print('onnxruntime:', ort.__version__)
    print('providers:', ort.get_available_providers())
except ImportError:
    print('onnxruntime not installed; skipping optional import')
PY

echo "[CI:NODE1] HTTP clients"
"$PYTHON_BIN" - <<'PY'
import httpx, httpx2
print('httpx:', httpx.__version__)
print('httpx2: OK')
PY

echo "[CI:NODE1] SQLite schema smoke"
TMP_DB="/tmp/ai_camera_ci_$$.db"
"$PYTHON_BIN" - <<PY
from services.common.event_db import EventDB
p = '$TMP_DB'
db = EventDB(p)
db.upsert_camera('ci_camera','CI Camera','usb_rtp','127.0.0.1','ci',True)
print(db.list_cameras())
PY
rm -f "$TMP_DB"

echo "[CI:NODE1] API module import"
"$PYTHON_BIN" - <<'PY'
import services.node1_api_gateway.app as app
print('Node1 API app import OK:', app.app.title)
PY

echo "[CI:NODE1] Runtime validation PASS"
