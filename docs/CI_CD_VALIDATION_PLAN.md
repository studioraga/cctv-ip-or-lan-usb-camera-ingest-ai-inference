# CI/CD Validation Plan

This project has both normal software checks and hardware-in-the-loop checks. Standard GitHub-hosted CI can validate syntax and non-hardware logic. Camera streaming tests require Node1/Node2 hardware or self-hosted runners.

---

## 1. CI layers

### Layer 1 — Static validation, no hardware

Run on every commit:

```bash
./scripts/ci/validate_static.sh
```

Checks:

- Python compile checks for agents and services.
- YAML syntax for configs/policies.
- Shell script syntax.
- Node2 GStreamer command generation for every profile.
- Query parser smoke test.

### Layer 2 — Node1 local runtime smoke

Run on Node1 or a compatible local machine:

```bash
./scripts/ci/validate_node1_runtime.sh
```

Checks:

- OpenCV import.
- OpenCV GStreamer build visibility.
- ONNX Runtime import.
- SQLite schema initialization.
- Event DB smoke insert/list.
- Node1 API module import.

### Layer 3 — Node2 local runtime smoke

Run on Node2 Jetson:

```bash
./scripts/ci/validate_node2_runtime.sh
```

Checks:

- Node2 controller imports.
- Generated GStreamer commands for all profiles.
- YUYV profile includes `videoconvert` and `UYVY` before `rtpvrawpay`.
- FastAPI control app imports.

### Layer 4 — Hardware-in-the-loop LAN validation

Run manually or with self-hosted runners:

1. Start Node2 control agent.
2. Start Node1 receiver.
3. Start stream through REST.
4. Confirm receiver FPS/frame output.
5. Stop stream.
6. Confirm receiver exits after no-frame timeout.
7. Confirm motion events create DB rows, keyframes, and clips.

---

## 2. Future GitHub Actions skeleton

A future `.github/workflows/ci.yml` can run Layer 1 checks:

```yaml
name: ci
on: [push, pull_request]

jobs:
  static:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install minimal deps
        run: |
          python -m pip install --upgrade pip
          pip install PyYAML pydantic fastapi prometheus-client httpx qdrant-client
      - name: Static validation
        run: ./scripts/ci/validate_static.sh
```

Hardware tests should not run on public GitHub-hosted runners unless camera/network dependencies are mocked. Use self-hosted runners on Node1/Node2 if full LAN validation is required.

---

## 3. Suggested pre-push checklist

```bash
./scripts/ci/validate_static.sh
./scripts/ci/validate_node1_runtime.sh   # Node1 only
./scripts/ci/validate_node2_runtime.sh   # Node2 only
```

Manual hardware test:

```bash
# Node2
./scripts/node2/run_node2_control_agent.sh

# Node1
python agents/node1/node1_receiver_agent.py \
  --profile mjpeg_720p30 \
  --port 5000 \
  --camera-id c922_node2_gate \
  --db-path data/events/ai_camera.db \
  --metrics --metrics-port 9101 \
  --motion-events \
  --no-frame-timeout-sec 10 \
  --startup-timeout-sec 30 \
  --event-log results/node1/events.jsonl

# Node1 or any LAN terminal
curl -X POST http://192.168.29.188:8082/stream/start \
  -H 'Content-Type: application/json' \
  -d '{"node1_ip":"192.168.29.20","port":5000,"profile":"mjpeg_720p30","device":"/dev/video0"}'

curl -X POST http://192.168.29.188:8082/stream/stop
```
