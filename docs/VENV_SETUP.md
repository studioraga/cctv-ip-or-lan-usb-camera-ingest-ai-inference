# Python virtual environment setup for Node1 and Node2

This project should not run against uncontrolled system Python, but Node1 and Node2 must use architecture-local virtual environments. Never copy `.venv` between Node1 x86_64 and Node2 Jetson aarch64.

## Critical Node1 rule: OpenCV must have GStreamer enabled

Node1 receives RTP/JPEG through an OpenCV `VideoCapture(..., cv2.CAP_GSTREAMER)` pipeline. Therefore Node1 `.venv` must see the apt-installed `python3-opencv` package that was built with GStreamer support.

Validated failure:

```text
opencv: 4.13.0
GStreamer: NO
[ERROR] Failed to open GStreamer pipeline
```

Validated fix:

```text
python3 -m venv --system-site-packages .venv
opencv: 4.6.0
GStreamer: YES (1.24.1)
```

Do not install `opencv-python` or `opencv-contrib-python` into Node1 `.venv`.

## Node1 setup

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"

# Recreate if an existing venv reports GStreamer: NO.
RECREATE_VENV=1 ./scripts/node1/setup_node1_venv.sh
source .venv/bin/activate

python - <<'PY'
import cv2
print(cv2.__version__)
for line in cv2.getBuildInformation().splitlines():
    if "GStreamer" in line:
        print(line)
PY
```

Expected:

```text
GStreamer: YES
```

## Node2 setup

Node2 controls the C922/V4L2/GStreamer sender. Streaming is performed by GStreamer, but the control API requires FastAPI/Pydantic/Prometheus plus `httpx` and `httpx2` for test compatibility.

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
RECREATE_VENV=1 ./scripts/node2/setup_node2_venv.sh
source .venv/bin/activate
python -m agents.node2.node2_streamer_controller --help
```

## Dependency files

- `requirements-node1.txt` includes Node1 API, receiver, ONNX Runtime, tests, `httpx`, and `httpx2`.
- `requirements-node2.txt` includes Node2 control-agent/runtime dependencies, `httpx`, and `httpx2`.

## Source sync pattern

From Node1/control machine:

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
AI_CAMERA_NODE2_USER=srrmk AI_CAMERA_NODE2_IP=192.168.29.188 \
  ./scripts/common/sync_repo_to_node2.sh
```

The sync excludes `.venv`, `.venv.backup-*`, `__pycache__`, pyc files, results, SQLite DB/WAL/SHM files, clips, and generated keyframes.
