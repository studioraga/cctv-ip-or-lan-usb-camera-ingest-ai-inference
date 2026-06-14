#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
RECREATE_VENV="${RECREATE_VENV:-0}"

cat <<'NOTE'
[Node1 venv rule]
Node1 receiver uses OpenCV VideoCapture with GStreamer pipelines.
Therefore Node1 .venv MUST be created with --system-site-packages so it can see apt python3-opencv.
Do not install opencv-python/opencv-contrib-python in this venv.
NOTE

if [ "$RECREATE_VENV" = "1" ] && [ -d "$VENV_DIR" ]; then
  mv "$VENV_DIR" "${VENV_DIR}.backup-$(date +%Y%m%d-%H%M%S)"
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-node1.txt

python - <<'PY'
import sys
print("Python:", sys.executable)
try:
    import cv2
    print("cv2 version:", cv2.__version__)
    line = next((x for x in cv2.getBuildInformation().splitlines() if "GStreamer" in x), None)
    print(line or "GStreamer line not found")
    if line is None or "YES" not in line:
        raise SystemExit("[FAIL] Node1 OpenCV must report GStreamer: YES. Recreate venv with --system-site-packages and ensure apt python3-opencv is installed.")
except Exception as exc:
    raise SystemExit(f"[FAIL] cv2/GStreamer validation failed: {exc}")
try:
    import onnxruntime as ort
    print("onnxruntime:", ort.__version__)
    print("providers:", ort.get_available_providers())
except Exception as exc:
    print("onnxruntime check failed:", exc)
try:
    import httpx, httpx2
    print("httpx:", httpx.__version__)
    print("httpx2: OK")
except Exception as exc:
    raise SystemExit(f"[FAIL] HTTP client dependency check failed: {exc}")
PY

echo "Node1 .venv ready at: $REPO_ROOT/$VENV_DIR"
echo "Activate with: source $VENV_DIR/bin/activate"
