# CI/CD and validation plan

This project has both normal software checks and hardware-in-the-loop checks. Hosted CI can validate syntax, imports, policy, migrations, Docker/Grafana provisioning, and command construction. Full streaming and capture-session validation require Node1/Node2 hardware or self-hosted LAN runners.

## Layer 1 — static validation, no hardware

Run from any checkout:

```bash
./scripts/ci/validate_static.sh
```

Covers:

- Python compile checks.
- YAML syntax checks for base configs and policies.
- Shell syntax checks.
- Node2 GStreamer command generation smoke tests.
- Query parser smoke test.
- Step 13 validation script syntax.

## Layer 2 — unit and integration tests

```bash
source .venv/bin/activate
python3 -m pytest -q
```

Current expected result on Node1 after Step 13:

```text
27 passed, 4 FastAPI on_event deprecation warnings
```

The warnings are non-fatal. They indicate a future FastAPI lifespan migration task.

## Layer 3 — Node1 runtime validation

Run on Node1 only:

```bash
./scripts/ci/validate_node1_runtime.sh
```

Covers:

- Node1 `.venv` exists and is active.
- OpenCV imports from apt/system packages.
- `cv2.getBuildInformation()` reports `GStreamer: YES`.
- ONNX Runtime imports for Node1 inference-worker features.
- API/capture dependencies import successfully.

Failure signature:

```text
GStreamer: NO
```

Fix:

```bash
RECREATE_VENV=1 ./scripts/node1/setup_node1_venv.sh
```

## Layer 4 — Node2 runtime validation

Run on Node2 only:

```bash
PYTHONNOUSERSITE=1 ./scripts/ci/validate_node2_runtime.sh
```

Covers:

- User-site packages are disabled.
- FastAPI/Pydantic/Prometheus/httpx/httpx2 dependencies import cleanly.
- Node2 GStreamer command builder works.
- Node2 runtime remains isolated from Node1 OpenCV/ONNX dependencies.

YOLO tests are Node1 inference tests and should skip cleanly on Node2 if optional inference dependencies are absent.

## Layer 5 — reproducible deployment preparation

```bash
RUN_PREPARE=1 ./scripts/validate_step10_reproducible_deployment.sh node1
RUN_PREPARE=1 ./scripts/validate_step10_reproducible_deployment.sh node2
```

Covers:

- Runtime config rendering.
- Policy validation.
- SQLite migrations.
- Systemd unit rendering.
- Path portability under the current checkout root.

## Layer 6 — hardware streaming validation

Production RTP validation from Node1:

```bash
./scripts/validate_step9_streaming.sh
```

Receiver-side bounded-slices validation from Node1:

```bash
./scripts/validate_step11_latency_monitoring.sh
```

Timestamped E2E validation from Node1:

```bash
./scripts/validate_step12_e2e_latency.sh
```

Step 12 temporarily stops the production Node1 receiver so it can bind UDP `5000` and metrics `9101`, then restarts it.

## Layer 7 — YOLO ONNX validation

```bash
./scripts/validate_step12_yolo_onnx.sh
```

This always runs synthetic postprocess tests on Node1. To include the real-model smoke, download and pin the default model first:

```bash
./scripts/models/download_yolo_onnx.sh
./scripts/validate_step12_yolo_onnx.sh
```

Default path:

```text
AI_CAMERA_YOLO_MODEL=models/object_detection/yolo11n.onnx
```

## Layer 8 — Grafana/Prometheus provisioning validation

```bash
./scripts/validate_step13_grafana_stack.sh
```

Covers:

- Renders `configs/runtime/prometheus.yml`.
- Validates generated Prometheus YAML.
- Validates Grafana datasource provisioning YAML.
- Validates Grafana dashboard provider YAML.
- Validates dashboard JSON.
- Runs `docker compose config`.

The runtime compose paths must account for the compose file location under `docker/`:

```yaml
../configs/runtime/prometheus.yml:/etc/prometheus/prometheus.yml:ro
./grafana/provisioning:/etc/grafana/provisioning:ro
./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

## Layer 9 — Step 13 capture-session hardware validation

Run from trusted Node1:

```bash
./scripts/validate_step13_capture_session.sh
```

Covers:

- Node1 API health.
- Node2 control health.
- POST `/capture/sessions`.
- Capture status polling.
- Dataset directory creation.
- Source JPEG frame count.
- `manifest.json`, `metadata/frames.jsonl`, `metrics_summary.json`, `report.md`, optional `preview.mp4`.
- Prometheus capture metrics on Node1 API.
- Node2 stream stop after capture.

Expected pass:

```text
[OK] Step 13 capture-session dataset validation completed
```

## Layer 10 — source hygiene before commit

Run before creating a source archive or pushing:

```bash
git status --short
git diff --cached --stat
```

Do not stage runtime/generated paths:

```text
.venv/
configs/runtime/*.yml
results/
data/events/*.db*
data/datasets/
docker/configs/
docker/docker/
__pycache__/
```

## Known non-fatal warnings

| Warning | Meaning | Follow-up |
|---|---|---|
| FastAPI `on_event` deprecation | Startup hook works but should move to lifespan API later | Future cleanup |
| Node2 local `/stream/status` 403 | Node2 is not a trusted control client by default | Query from Node1 or explicitly add Node2 to allow-list |
| Step 13 histogram count exceeds latest frames gauge | Histogram is cumulative for API process lifetime | Normal Prometheus behavior |
