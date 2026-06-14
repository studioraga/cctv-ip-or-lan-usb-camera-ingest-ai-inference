# CI/CD Validation Plan

This project has both normal software checks and hardware-in-the-loop checks. Hosted CI can validate syntax, imports, policy, migrations, and GStreamer command construction. Full stream validation requires Node1/Node2 hardware or self-hosted LAN runners.

## Layer 1 — static validation, no hardware

```bash
./scripts/ci/validate_static.sh
```

Checks:

- Python compile checks for agents and services.
- YAML syntax for configs and policies.
- Shell script syntax.
- Node2 GStreamer command generation for every profile.
- Query parser smoke test.

## Layer 2 — Node1 local runtime smoke

Run on Node1 or a compatible x86 machine with apt OpenCV/GStreamer:

```bash
source .venv/bin/activate
./scripts/ci/validate_node1_runtime.sh
```

Checks:

- Python interpreter path.
- `cv2` import.
- `GStreamer: YES` in OpenCV build info. This is mandatory.
- ONNX Runtime import if installed.
- `httpx` and `httpx2` import.
- SQLite/EventDB smoke operation.
- Node1 API module import.

## Layer 3 — Node2 local runtime smoke

Run on Node2 Jetson:

```bash
source .venv/bin/activate
./scripts/ci/validate_node2_runtime.sh
```

Checks:

- Node2 dependency imports including `httpx` and `httpx2`.
- `agents.node2.node2_streamer_controller` import.
- Generated GStreamer commands for all profiles.
- MJPEG profiles include `rtpjpegpay`.
- YUYV raw profile includes `videoconvert`, `UYVY`, and `rtpvrawpay`.
- Node2 FastAPI control app import.
- Optional V4L2 camera probe.

## Layer 4 — deployment preparation

Run per node:

```bash
set -a; source deploy/ai-camera.env; set +a
export AI_CAMERA_REPO_ROOT="$PWD"
./scripts/common/prepare_deployment.sh node1
./scripts/common/prepare_deployment.sh node2
```

Expected: rendered runtime configs, policy validation, and pytest success.

## Layer 5 — hardware-in-the-loop Step 9 streaming validation

Run from Node1 after both systemd services are installed and active:

```bash
./scripts/validate_step9_streaming.sh
```

Checks:

1. Node1 `/health`.
2. Node2 `/health`.
3. Node2 `/stream/start` from trusted Node1.
4. Node2 `/stream/status` remains `running: true`.
5. Node1 receiver metrics show FPS and increasing `ai_camera_frames_total`.
6. Node2 `/stream/stop` returns `running: false`.

The script writes a timestamped log under `results/step9/`.

## Known failure signatures that CI should catch or document

| Failure | Meaning | Fix |
|---|---|---|
| `GStreamer: NO` in Node1 `.venv` | PyPI/OpenCV wheel shadowed apt OpenCV | Recreate venv with `--system-site-packages`; do not install `opencv-python` |
| `ModuleNotFoundError: services` in receiver | Receiver launched as direct script | Launch with `python -m agents.node1.node1_receiver_agent` |
| `/stream/status` returns `403` from Node2 itself | Caller not in Node2 trusted control list | Query status from Node1 or add explicit policy entry if desired |
| `Device '/dev/video0' is busy` | Manual sender or stale gst process owns camera | Stop previous sender before API start |
| `streamer exited rc=1` | GStreamer command failed after API start | Check Node2 journal and camera ownership |
