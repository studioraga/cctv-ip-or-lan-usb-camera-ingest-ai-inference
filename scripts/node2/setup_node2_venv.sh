#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

sudo apt update
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  v4l-utils \
  ffmpeg \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav

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
try:
    import yaml
    print("PyYAML import: OK")
except Exception as exc:
    print("PyYAML check failed:", exc)
PY

echo "Node2 .venv ready at: $REPO_ROOT/$VENV_DIR"
echo "Activate with: source $VENV_DIR/bin/activate"
