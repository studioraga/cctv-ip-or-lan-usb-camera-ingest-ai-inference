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

# Node2 should use an isolated venv. The Jetson camera path is owned by
# GStreamer/V4L2 command-line tools, not Python OpenCV, so Node2 does not need
# --system-site-packages. Keeping the venv isolated prevents ~/.local or apt
# Python packages from mixing with FastAPI/Starlette/AnyIO and breaking the
# control API at runtime.
export PYTHONNOUSERSITE=1

if [ "$RECREATE_VENV" = "1" ] && [ -d "$VENV_DIR" ]; then
  mv "$VENV_DIR" "${VENV_DIR}.backup-$(date +%Y%m%d-%H%M%S)"
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel
PYTHONNOUSERSITE=1 python -m pip install --no-cache-dir -r requirements-node2.txt

python - <<'PY'
import site
import sys

print("Python:", sys.executable)
print("ENABLE_USER_SITE:", site.ENABLE_USER_SITE)
if site.ENABLE_USER_SITE:
    raise SystemExit("Node2 venv must disable user-site packages; export PYTHONNOUSERSITE=1")

bad_paths = [p for p in sys.path if "/.local/" in p]
if bad_paths:
    raise SystemExit(f"Node2 venv is contaminated by user-site paths: {bad_paths}")

for name in ("yaml", "fastapi", "uvicorn", "pydantic", "prometheus_client", "httpx", "httpx2"):
    __import__(name)
    print(name, "OK")

import anyio
import anyio._core._tasks as anyio_tasks
import anyio._backends._asyncio  # noqa: F401
print("anyio:", anyio.__file__)
print("anyio TaskHandle:", hasattr(anyio_tasks, "TaskHandle"))
if not hasattr(anyio_tasks, "TaskHandle"):
    raise SystemExit("Broken AnyIO install: missing TaskHandle")

from agents.node2.node2_streamer_controller import build_gstreamer_command
cmd = build_gstreamer_command("mjpeg_720p30", "192.0.2.21", 5000, "/dev/video0")
print("dry-run:", " ".join(cmd))
PY

python -m pip check

echo "Node2 .venv ready at: $REPO_ROOT/$VENV_DIR"
echo "Activate with: source $VENV_DIR/bin/activate"
echo "Recommended runtime export: export PYTHONNOUSERSITE=1"
