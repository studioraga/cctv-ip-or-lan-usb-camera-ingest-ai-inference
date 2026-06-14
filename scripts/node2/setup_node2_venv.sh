#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
RECREATE_VENV="${RECREATE_VENV:-0}"

sudo apt update
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  v4l-utils \
  ffmpeg \
  sqlite3 \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav

if [ "$RECREATE_VENV" = "1" ] && [ -d "$VENV_DIR" ]; then
  mv "$VENV_DIR" "${VENV_DIR}.backup-$(date +%Y%m%d-%H%M%S)"
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-node2.txt

python - <<'PY'
import sys
print("Python:", sys.executable)
for name in ("yaml", "fastapi", "uvicorn", "pydantic", "prometheus_client", "httpx", "httpx2"):
    __import__(name)
    print(name, "OK")
from agents.node2.node2_streamer_controller import build_gstreamer_command
cmd = build_gstreamer_command("mjpeg_720p30", "192.0.2.21", 5000, "/dev/video0")
print("dry-run:", " ".join(cmd))
PY

echo "Node2 .venv ready at: $REPO_ROOT/$VENV_DIR"
echo "Activate with: source $VENV_DIR/bin/activate"
