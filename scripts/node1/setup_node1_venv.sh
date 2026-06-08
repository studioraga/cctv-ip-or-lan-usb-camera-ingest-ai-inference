#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

#sudo apt update
#sudo apt install -y \
#  python3 \
#  python3-venv \
#  python3-pip \
#  python3-opencv \
#  gstreamer1.0-tools \
#  gstreamer1.0-plugins-base \
#  gstreamer1.0-plugins-good \
#  gstreamer1.0-plugins-bad \
#  gstreamer1.0-plugins-ugly \
#  gstreamer1.0-libav

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
    info = cv2.getBuildInformation()
    for line in info.splitlines():
        if "GStreamer" in line:
            print(line)
except Exception as exc:
    print("cv2 import/check failed:", exc)
try:
    import onnxruntime as ort
    print("onnxruntime:", ort.__version__)
    print("providers:", ort.get_available_providers())
except Exception as exc:
    print("onnxruntime check failed:", exc)
PY

echo "Node1 .venv ready at: $REPO_ROOT/$VENV_DIR"
echo "Activate with: source $VENV_DIR/bin/activate"
