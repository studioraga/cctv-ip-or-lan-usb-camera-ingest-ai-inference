#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
sudo apt update
sudo apt install -y python3-full python3-venv python3-pip python3-opencv python3-numpy \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-node1.txt
python - <<'PY'
import cv2
print('OpenCV:', cv2.__version__)
print(next((x for x in cv2.getBuildInformation().splitlines() if 'GStreamer' in x), 'GStreamer line not found'))
PY
