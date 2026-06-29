# CCTV/IP or LAN USB Camera Ingest + AI Inference Platform

A **local-first AI camera platform** validated on a two-node LAN. Node2 owns a Logitech C922 USB camera and streams frames to Node1. Node1 provides the API gateway, production RTP receiver, timestamped capture-session pipeline, SQLite metadata, source-JPEG datasets, Prometheus metrics, and a Grafana dashboard for the demo.

The system is intentionally local. Camera frames, source-JPEG datasets, events, clips, keyframes, SQLite metadata, policies, and future embeddings remain inside the LAN unless explicitly exported.

---

## 1. Validated topology

| Node | Validated host/IP | Role | Main services |
|---|---|---|---|
| Node1 | `sr-kaaldev` / `192.168.29.20` | API gateway, production receiver, capture-session orchestrator, event/dataset DB, Prometheus/Grafana stack | `node1-ai-camera-api.service`, `node1-ai-camera-receiver.service`, Docker Prometheus/Grafana/Qdrant |
| Node2 | `shiva-vaisesika` / `192.168.29.188` | Jetson camera streamer and control agent | `node2-camera-control-agent.service` |

Default ports:

```text
Node2 -> Node1 RTP/JPEG production stream:      UDP 5000
Node2 -> Node1 timestamped capture stream:     UDP 5001
Node1 API gateway + capture UI + API metrics:  http://192.168.29.20:8080
Node1 receiver metrics:                        http://192.168.29.20:9101/metrics
Node2 control agent + metrics:                 http://192.168.29.188:8082
Prometheus:                                    http://192.168.29.20:9090
Grafana:                                       http://192.168.29.20:3000
Qdrant scaffold:                               http://192.168.29.20:6333
```

Production RTP path:

```text
Logitech C922 USB camera
  -> Node2 /dev/video0 through V4L2
  -> GStreamer MJPEG RTP sender
  -> UDP/RTP port 5000 over LAN
  -> Node1 GStreamer/OpenCV receiver
  -> BGR frames [720, 1280, 3]
  -> receiver FPS / bounded-slices latency metrics
  -> motion events
  -> JSONL + SQLite + keyframe JPG + clip MP4
```

Step 13 capture-session path:

```text
Grafana dashboard / Node1 /ui/capture
  -> POST Node1 /capture/sessions
  -> Node1 validates duration <= 7200 sec and policy target 192.168.29.20:5001
  -> Node1 starts a timestamped dataset receiver on UDP 5001
  -> Node1 asks Node2 /stream/start with transport=timed_jpeg_udp
  -> Node2 sends source JPEG frames with frame_id + sender timestamps
  -> Node1 writes data/datasets/{session_id}/frames/*.jpg
  -> Node1 writes metadata/frames.jsonl, manifest.json, metrics_summary.json, report.md, optional preview.mp4
  -> Prometheus scrapes capture metrics from Node1 API
  -> Grafana shows capture status, frame/byte counts, and latency panels
```

---

## 2. Fresh-start correction from the latest Node1/Node2 logs

The attached fresh-start logs showed this sequence:

```text
Step 9 production RTP validation: PASS
Step 11 bounded-slices validation: FAIL
curl: (7) Failed to connect to 192.168.29.20 port 9101: Couldn't connect to server
```

This was not a Node2 camera failure. Node2 `/health` was healthy, Node2 `/stream/start` returned `running: true`, and Step 9 proved that RTP frames were flowing.

The failure was caused by two README/deployment gaps:

1. **Old Node1 services were still running from a stale repo path.**  
   The shell was in:

   ```text
   /home/rmk/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference
   ```

   but `systemctl status` showed both Node1 services still executing from:

   ```text
   /home/rmk/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference
   ```

   The old README used `systemctl enable --now ...`. That starts a service only when it is not already running. It does **not** restart an already-running service after regenerating a unit file. The fixed README now uses `systemctl enable ...` followed by `systemctl restart ...`.

2. **The production receiver service exited when the sender stopped between validations.**  
   Step 9 stops the Node2 sender at the end. The receiver agent default watchdog can exit after no frames are received. That is useful for manual foreground runs, but it is wrong for a long-running production systemd receiver because the metrics endpoint on port 9101 can disappear between Step 9 and Step 11. The systemd template now launches Node1 receiver with:

   ```text
   --no-exit-on-no-frames
   ```

   That keeps UDP 5000 and metrics 9101 alive even when the Node2 stream is temporarily stopped.

The correct fresh-start rule is: **after installing systemd units, always run `daemon-reload`, `enable`, and `restart`; then verify that the running service command path matches the current repo path.**

---

## 3. Current validation milestone

| Area | Status | Evidence |
|---|---:|---|
| Node1 API service | PASS after restart | `/health` returns `node1_api_gateway`, policy version 2 |
| Node1 receiver service | PASS after restart | active systemd service, default `--transport rtp`, UDP 5000, metrics 9101, `--no-exit-on-no-frames` |
| Node1 OpenCV/GStreamer | PASS | `.venv` sees apt OpenCV `GStreamer: YES` |
| Node2 control service | PASS after restart | `/health` returns `node2_control_agent`, policy version 2 |
| Node2 camera mode | PASS | `/dev/video0`, MJPG 1280x720 at 30 FPS available |
| API-controlled RTP stream | PASS | Node1 starts/stops Node2 RTP sender and Node1 frames increase |
| Step 11 latency monitoring | PASS when Node1 receiver remains alive | bounded-slices metrics exported for `frame_gap_ms`, `capture_read_ms`, `capture_queue_wait_ms` |
| Step 12 E2E latency | PASS | `timed_jpeg_udp` exports frame IDs and sender-to-Node1 latency metrics |
| YOLO ONNX postprocess | PASS | generic YOLOv5/YOLOv8 decoder unit tests pass; real model smoke is optional |
| Step 13 capture sessions | PASS | UI/API capture writes source JPEG dataset and artifacts under `data/datasets/` |
| Prometheus stack | PASS | generated `configs/runtime/prometheus.yml` mounted into container and health endpoint is green |
| Grafana provisioning | PASS | dashboard `AI Camera / AI Camera Capture Session Demo` appears after provisioning path fix |

Latest Step 12 fresh-start validation from the attached Node1/Node2 logs:

```text
Node1 prepare_deployment.sh node1: 27 passed, 4 warnings
Node2 prepare_deployment.sh node2: 23 passed, 1 skipped, 4 warnings
Step 9 production RTP validation: PASS; frames_total increased
Step 11 bounded-slices latency validation: PASS; frames_first=36.0 frames_last=251.0 latency_seen=1
Step 12 timestamped JPEG/UDP E2E validation: PASS; frames_first=33.0 frames_last=309.0 e2e_seen=1
Step 12 YOLO ONNX postprocess validation: PASS; 4 passed in 0.13s
Real YOLO model smoke: optional; run ./scripts/models/download_yolo_onnx.sh or Node1 startup with --download-yolo to pin models/object_detection/yolo11n.onnx
```

`ai_camera_latency_window_violation=1` in Step 11/12 is not a script failure. It means the rolling latency variation exceeded the configured `AI_CAMERA_LATENCY_THRESHOLD_MS=5.0` threshold for that metric window. The validation goal at this stage is that frame counters increase and the bounded-slices/E2E metrics are exported correctly; those violation metrics are now available for tuning and dashboarding.

---

## 4. Critical runtime rules

### 4.1 Node1 OpenCV/GStreamer rule

Node1 receiver uses OpenCV `VideoCapture(..., cv2.CAP_GSTREAMER)`. Node1 `.venv` must therefore use apt/system OpenCV with GStreamer support.

Bad state:

```text
opencv: 4.13.0
GStreamer: NO
[ERROR] Failed to open GStreamer pipeline
```

Fixed state:

```text
python3 -m venv --system-site-packages .venv
opencv: 4.6.0 or system-provided OpenCV
GStreamer: YES
```

Do **not** install `opencv-python` or `opencv-contrib-python` into Node1 `.venv`.

### 4.2 Node-local environment rule

`deploy/ai-camera.env` is node-local. Do not reuse a Node2 copy on Node1 or an old `mig1` copy under a new `ai-sys1` checkout.

For a fresh checkout, regenerate it:

```bash
rm -f deploy/ai-camera.env
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Leave this value blank unless you intentionally need an absolute override:

```text
AI_CAMERA_REPO_ROOT=
```

The deployment commands export the correct current path with:

```bash
export AI_CAMERA_REPO_ROOT="$PWD"
```

### 4.3 Systemd restart rule

After regenerating systemd unit files, `enable --now` is not enough when the service is already running. Use:

```bash
sudo systemctl daemon-reload
sudo systemctl enable <service-name>
sudo systemctl restart <service-name>
```

For Node1, restart both services together:

```bash
sudo systemctl enable node1-ai-camera-api.service node1-ai-camera-receiver.service
sudo systemctl restart node1-ai-camera-api.service node1-ai-camera-receiver.service
```

For Node2:

```bash
sudo systemctl enable node2-camera-control-agent.service
sudo systemctl restart node2-camera-control-agent.service
```

### 4.4 Startup scripts for repeatable Node1/Node2 bring-up

The validated fresh-start sequence is now captured in node-local startup scripts. Run Node2 first, then Node1.

First-time dependency setup:

```bash
# Node2 / Jetson
cd "$HOME/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
./scripts/startup/node2_startup_steps12.sh --install-deps

# Node1 / workstation
cd "$HOME/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
./scripts/startup/node1_startup_steps12.sh --install-deps --run-validations
```

Normal restart after dependencies are already installed:

```bash
# Node2
./scripts/startup/node2_startup_steps12.sh

# Node1
./scripts/startup/node1_startup_steps12.sh --run-validations
```

The Node1 startup script runs Step 9, Step 11, Step 12 E2E, and Step 12 YOLO validation only when `--run-validations` is provided. Startup logs are written under `results/startup/`. See `docs/STARTUP_SCRIPTS.md`.

---

## 5. Repository layout

```text
agents/
  node1/node1_receiver_agent.py          # Node1 RTP/timed JPEG receiver + metrics + events
  node2/node2_streamer_controller.py     # Node2 GStreamer RTP command builder/runner
  node2/node2_timed_jpeg_sender.py       # Node2 timestamped JPEG/UDP sender for E2E/datasets
services/
  common/                                # policy, migrations, DB, path security, timed frame protocol
  node1_api_gateway/                     # Node1 FastAPI API gateway + capture UI
  node1_capture_orchestrator/            # Step 13 capture-session manager and dataset writer
  node2_control_agent/                   # Node2 FastAPI camera control service
scripts/
  common/                                # deployment render/install/sync helpers
  startup/                               # idempotent Node1/Node2 startup scripts through Step 12
  ci/                                    # static and node-local validation scripts
  validate_step9_streaming.sh            # production RTP validation
  validate_step11_latency_monitoring.sh  # bounded-slices validation
  validate_step12_e2e_latency.sh         # timestamped E2E validation
  validate_step13_capture_session.sh     # dataset capture validation
  validate_step13_grafana_stack.sh       # Grafana/Prometheus provisioning validation
docker/
  docker-compose.node1.yml               # Node1 Prometheus/Grafana/Qdrant stack
  grafana/                               # provisioned datasource and dashboard
migrations/                              # SQLite migrations, including capture sessions
configs/runtime/                         # generated runtime configs, not hand-edited
data/datasets/                           # runtime capture datasets, ignored by git
docs/                                    # architecture, deployment, CI, validation notes
```

Generated runtime artifacts such as `.venv`, `.venv.backup-*`, `results/`, SQLite DB/WAL/SHM files, clips, keyframes, datasets, generated runtime config, Docker accidental mount directories, `__pycache__`, and pyc files are excluded from clean source sync/archive outputs.

---

## 6. Node1 setup and service deployment

Run on Node1:

```bash
cd "$HOME/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
rm -f deploy/ai-camera.env
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Edit `deploy/ai-camera.env` for Node1:

```text
AI_CAMERA_NODE_ROLE=node1
AI_CAMERA_REPO_ROOT=
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
AI_CAMERA_PROFILE=mjpeg_720p30
AI_CAMERA_CAMERA_ID=c922_node2_gate
AI_CAMERA_NODE1_RTP_PORT=5000
AI_CAMERA_CAPTURE_UDP_PORT=5001
AI_CAMERA_DATASET_ROOT=data/datasets
AI_CAMERA_CAPTURE_MAX_DURATION_SEC=7200
AI_CAMERA_EVENT_LOG=results/node1/events.jsonl
AI_CAMERA_API_CLIENTS=192.168.29.20,127.0.0.1,::1
```

Install dependencies and create Node1 `.venv`:

```bash
scripts/node1/install_node1_dependencies.sh
RECREATE_VENV=1 scripts/node1/setup_node1_venv.sh
source .venv/bin/activate
export PYTHONNOUSERSITE=1
```

Verify OpenCV/GStreamer:

```bash
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
GStreamer:                   YES
```

Prepare, install, enable, and restart Node1 systemd units:

```bash
set -a; source deploy/ai-camera.env; set +a
export AI_CAMERA_REPO_ROOT="$PWD"

./scripts/common/prepare_deployment.sh node1

sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_CAPTURE_UDP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_TRANSPORT,AI_CAMERA_DATASET_ROOT,AI_CAMERA_CAPTURE_MAX_DURATION_SEC,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG,AI_CAMERA_LATENCY_THRESHOLD_MS,AI_CAMERA_LATENCY_WINDOW_SAMPLES \
  "$PWD/.venv/bin/python" scripts/common/install_systemd_units.py --role node1

sudo systemctl daemon-reload
sudo systemctl enable node1-ai-camera-api.service node1-ai-camera-receiver.service
sudo systemctl restart node1-ai-camera-api.service node1-ai-camera-receiver.service
```

Validate Node1 service path, health, metrics, and UDP listener:

```bash
systemctl status node1-ai-camera-api.service --no-pager --full
systemctl status node1-ai-camera-receiver.service --no-pager --full

# The status output must show the current repo path, not an old mig1 path.
pgrep -af 'node1_receiver_agent|uvicorn services.node1_api_gateway' | grep "$PWD"

curl -fsS http://192.168.29.20:8080/health | python3 -m json.tool
curl -fsS http://192.168.29.20:9101/metrics | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total|ai_camera_decode_failures_total' -A 2
sudo ss -lunp | grep ':5000'
```

Expected receiver service command includes:

```text
-m agents.node1.node1_receiver_agent ... --transport rtp ... --metrics-port 9101 ... --no-exit-on-no-frames
```

Expected UDP listener:

```text
UNCONN ... 0.0.0.0:5000 ... users:(("python",pid=...,fd=...))
```

---

## 7. Node2 setup and service deployment

Run on Node2:

```bash
cd "$HOME/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
rm -f deploy/ai-camera.env
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Edit `deploy/ai-camera.env` for Node2:

```text
AI_CAMERA_NODE_ROLE=node2
AI_CAMERA_REPO_ROOT=
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
AI_CAMERA_DEVICE=/dev/video0
AI_CAMERA_PROFILE=mjpeg_720p30
AI_CAMERA_TRANSPORT=rtp
AI_CAMERA_API_CLIENTS=192.168.29.20,127.0.0.1,::1
```

Install dependencies and create Node2 `.venv`:

```bash
scripts/node2/install_node2_dependencies.sh
PYTHONNOUSERSITE=1 RECREATE_VENV=1 scripts/node2/setup_node2_venv.sh
source .venv/bin/activate
export PYTHONNOUSERSITE=1
```

Verify camera mode:

```bash
v4l2-ctl --device=/dev/video0 --list-formats-ext | grep -A8 -B2 '1280x720'
```

Expected under MJPG: `1280x720` with `0.033s (30.000 fps)`.

Prepare, install, enable, and restart Node2 service:

```bash
set -a; source deploy/ai-camera.env; set +a
export AI_CAMERA_REPO_ROOT="$PWD"

./scripts/common/prepare_deployment.sh node2

sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_CAPTURE_UDP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_TRANSPORT,AI_CAMERA_DATASET_ROOT,AI_CAMERA_CAPTURE_MAX_DURATION_SEC,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG,PYTHONNOUSERSITE \
  "$PWD/.venv/bin/python" scripts/common/install_systemd_units.py --role node2

sudo systemctl daemon-reload
sudo systemctl enable node2-camera-control-agent.service
sudo systemctl restart node2-camera-control-agent.service
```

Validate Node2 from Node1:

```bash
curl -fsS http://192.168.29.188:8082/health | python3 -m json.tool
curl -fsS http://192.168.29.188:8082/stream/status | python3 -m json.tool
```

Note: `/stream/status`, `/stream/start`, and `/stream/stop` are policy-protected and should be called from trusted Node1. A 403 from Node2 itself is expected unless Node2 is also added to the trusted-control allow-list.

---

## 8. Production RTP stream validation from Node1

Before running validation, confirm Node1 receiver metrics is reachable:

```bash
curl -fsS http://192.168.29.20:9101/metrics >/dev/null
```

Run from Node1:

```bash
./scripts/validate_step9_streaming.sh
```

Manual equivalent:

```bash
curl -fsS -X POST http://192.168.29.188:8082/stream/start \
  -H 'Content-Type: application/json' \
  -d '{"camera_id":"c922_node2_gate","node1_ip":"192.168.29.20","port":5000,"device":"/dev/video0","profile":"mjpeg_720p30","transport":"rtp"}' | python3 -m json.tool

sleep 3
curl -fsS http://192.168.29.188:8082/stream/status | python3 -m json.tool

for i in 1 2 3 4 5; do
  curl -fsS http://192.168.29.20:9101/metrics | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total|ai_camera_decode_failures_total' -A 2
  sleep 1
done

curl -fsS -X POST http://192.168.29.188:8082/stream/stop | python3 -m json.tool
```

Expected metrics during stream:

```text
ai_camera_receiver_fps{camera_id="c922_node2_gate",profile="mjpeg_720p30"} > 0
ai_camera_frames_total{camera_id="c922_node2_gate",profile="mjpeg_720p30"} increasing
```

After the stream is stopped, this must still work because the systemd receiver uses `--no-exit-on-no-frames`:

```bash
curl -fsS http://192.168.29.20:9101/metrics >/dev/null
```

---

## 9. Step 11/12 latency and YOLO validation

Step 11 adds rolling bounded-slices stability monitoring for Node1 receiver timing:

```text
frame_gap_ms
capture_read_ms
capture_queue_wait_ms
```

Run from Node1 after Step 9:

```bash
./scripts/validate_step11_latency_monitoring.sh
```

Expected result:

```text
[OK] frames_total increased and bounded-slices latency metrics were exported
[OK] Step 11 latency monitoring validation completed
```

Step 12 adds timestamped JPEG/UDP E2E correlation and YOLO ONNX postprocessing:

```bash
./scripts/validate_step12_e2e_latency.sh
./scripts/validate_step12_yolo_onnx.sh
```

For the real-model smoke path, download and pin the default YOLO ONNX model on Node1:

```bash
./scripts/models/download_yolo_onnx.sh
./scripts/validate_step12_yolo_onnx.sh
```

The fixed repo-local model path is:

```text
AI_CAMERA_YOLO_MODEL=models/object_detection/yolo11n.onnx
```

The full Node1 startup shortcut is:

```bash
./scripts/startup/node1_startup_steps12.sh --install-deps --download-yolo --run-validations
```

The default production receiver remains:

```text
AI_CAMERA_TRANSPORT=rtp
```

Step 12/13 use `transport=timed_jpeg_udp` only when explicitly requested by validation scripts or capture sessions.

---

## 10. Step 13 Grafana capture-session demo

Recommended startup path for Step 13 on Node1:

```bash
./scripts/startup/node1_startup_step13.sh
```

For the full capture-session dataset validation as part of startup:

```bash
./scripts/startup/node1_startup_step13.sh --capture-test
```

Manual Grafana/Prometheus provisioning validation:

```bash
./scripts/common/render_prometheus_config.sh
./scripts/validate_step13_grafana_stack.sh
docker compose -f docker/docker-compose.node1.yml up -d
```

Important: run `scripts/common/render_prometheus_config.sh` before `docker compose up`. If Compose is run first while `configs/runtime/prometheus.yml` does not exist, Docker may create that path as a directory and Prometheus will fail with `not a directory: Are you trying to mount a directory onto a file`. The render script repairs that exact stale directory path and writes the expected file.

The compose file is under `docker/`, so relative mounts must be:

```yaml
../configs/runtime/prometheus.yml:/etc/prometheus/prometheus.yml:ro
./grafana/provisioning:/etc/grafana/provisioning:ro
./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

Health checks for the default hardened lab bind (`AI_CAMERA_OBSERVABILITY_BIND=127.0.0.1`):

```bash
curl -fsS http://127.0.0.1:9090/-/healthy
curl -fsS http://127.0.0.1:3000/api/health | python3 -m json.tool
curl -fsS -u "${GRAFANA_ADMIN_USER:-admin}:${GRAFANA_ADMIN_PASSWORD:-admin}" 'http://127.0.0.1:3000/api/search?query=AI%20Camera' | python3 -m json.tool
```

To expose Grafana/Prometheus to another LAN browser, set `AI_CAMERA_OBSERVABILITY_BIND=0.0.0.0` or `AI_CAMERA_OBSERVABILITY_BIND=192.168.29.20` in `deploy/ai-camera.env`, set a strong `GRAFANA_ADMIN_PASSWORD`, and rerun the Step 13 startup script. Grafana only applies `GF_SECURITY_ADMIN_PASSWORD` when its Docker volume is first initialized, so the startup script also resets the existing Grafana admin password to the value in `GRAFANA_ADMIN_PASSWORD` by default. Set `AI_CAMERA_GRAFANA_SYNC_ADMIN_PASSWORD=0` only if you manage Grafana credentials manually.

Open after LAN exposure is enabled:

```text
Grafana dashboard:
http://192.168.29.20:3000/d/ai-camera-capture-session-demo/ai-camera-capture-session-demo

Node1 capture form:
http://192.168.29.20:8080/ui/capture
```

Run a capture from the UI or through the API:

```bash
curl -fsS -X POST http://192.168.29.20:8080/capture/sessions \
  -H 'Content-Type: application/json' \
  -d '{
    "camera_id": "c922_node2_gate",
    "profile": "mjpeg_720p30",
    "duration_sec": 30,
    "device": "/dev/video0",
    "transport": "timed_jpeg_udp",
    "dataset_mode": "source_jpeg",
    "frame_stride": 1,
    "requested_by": "grafana-demo",
    "notes": "Grafana capture demo test"
  }' | python3 -m json.tool
```

Then validate artifacts:

```bash
SESSION_ID="cap_xxxxx"
DATASET_DIR="data/datasets/${SESSION_ID}"
find "$DATASET_DIR" -maxdepth 3 -type f | sort | head -30
cat "$DATASET_DIR/manifest.json" | python3 -m json.tool | head -80
cat "$DATASET_DIR/artifacts/metrics_summary.json" | python3 -m json.tool
cat "$DATASET_DIR/artifacts/report.md"
```

Automated validation:

```bash
./scripts/validate_step13_capture_session.sh
```

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl: (7) Failed to connect to 192.168.29.20 port 9101` after Step 9 | Node1 receiver exited after Node2 sender stopped, or old service is still running from stale path | Install updated unit, run `daemon-reload`, `enable`, and `restart`; verify service command includes current repo path and `--no-exit-on-no-frames` |
| `systemctl status` shows `/home/rmk/dev/pub/mig1/...` while shell is in `/home/rmk/dev/pub/ai-sys1/...` | Unit was regenerated but service was not restarted | Run `sudo systemctl restart node1-ai-camera-api.service node1-ai-camera-receiver.service` |
| Node1 receiver restart storm with `Failed to open GStreamer pipeline` | Node1 `.venv` OpenCV reports `GStreamer: NO` | Recreate Node1 venv with `RECREATE_VENV=1 scripts/node1/setup_node1_venv.sh`; do not install `opencv-python` into venv |
| `ModuleNotFoundError: services` in receiver | Receiver launched as script instead of module | Use generated systemd unit with `python -m agents.node1.node1_receiver_agent` |
| Node2 `/stream/status` returns 403 from Node2 shell | Policy trusts Node1 control IP | Run status from Node1 or update policy intentionally |
| Node2 stream exits rc=1 with `/dev/video0 busy` | Manual `gst-launch`, timed sender, or stale process owns camera | Stop manual sender; check `ps -ef | grep -E 'gst-launch|node2_timed_jpeg_sender|ffmpeg'`; retry |
| Frames do not increase on Node1 | Node1 receiver down, wrong RTP/capture port, firewall, or sender not running | Check systemd, `ss -lunp`, Node2 journal, and metrics |
| Prometheus container fails with `not a directory: Are you trying to mount a directory onto a file` | `configs/runtime/prometheus.yml` is missing or was accidentally created as a directory by an earlier Compose run | Run `./scripts/common/render_prometheus_config.sh`, then `docker compose -f docker/docker-compose.node1.yml up -d`; the render script removes the stale directory and writes the file |
| Grafana is healthy but dashboard is missing | Provisioning paths resolved relative to `docker/` incorrectly | Use `./grafana/provisioning` and `./grafana/dashboards` in compose; restart with `--force-recreate` |
| Capture session stays at `running frames=0` | Node2 stream not sending to UDP 5001, camera busy, or firewall blocks capture UDP | Check Node2 status/journal, `AI_CAMERA_CAPTURE_UDP_PORT`, and firewall |

Useful service checks:

```bash
systemctl status node1-ai-camera-api.service --no-pager --full
systemctl status node1-ai-camera-receiver.service --no-pager --full
journalctl -u node1-ai-camera-receiver.service -n 120 --no-pager
journalctl -u node2-camera-control-agent.service -n 120 --no-pager
pgrep -af 'node1_receiver_agent|uvicorn services.node1_api_gateway|node2_control_agent'
```

---

## 12. Development and CI checks

```bash
./scripts/ci/validate_static.sh
source .venv/bin/activate
python3 -m pytest -q
./scripts/ci/validate_node1_runtime.sh
./scripts/ci/validate_node2_runtime.sh
./scripts/common/prepare_deployment.sh node1
./scripts/common/prepare_deployment.sh node2
./scripts/validate_step9_streaming.sh
./scripts/validate_step11_latency_monitoring.sh
./scripts/validate_step12_e2e_latency.sh
./scripts/models/download_yolo_onnx.sh
./scripts/validate_step12_yolo_onnx.sh
./scripts/validate_step13_grafana_stack.sh
./scripts/validate_step13_capture_session.sh
```

See also:

- `docs/ARCHITECTURE.md`
- `docs/VENV_SETUP.md`
- `docs/PORTABLE_DEPLOYMENT.md`
- `docs/CI_CD_VALIDATION_PLAN.md`
- `docs/STEP11_BOUNDED_SLICES_LATENCY.md`
- `docs/STEP12_E2E_LATENCY_AND_YOLO.md`
- `docs/STEP13_GRAFANA_CAPTURE_DATASET.md`
- `docs/STARTUP_SCRIPTS.md`
- `docs/TASK1_IMPLEMENTATION_NOTES.md`
- `docs/GIT_COMMIT_MESSAGE_VALIDATION_MILESTONE.md`


## Step 14 — Motion-triggered Node1 live MP4 stream

Step 14 turns the Step 13 capture demo into a more meaningful product milestone:
Node2 reports motion, Node1 starts a bounded MP4-capable capture session, and LAN
clients can view/download the motion stream through Node1 API.

Start from the already-validated Node2/Node1 services:

```bash
# Node2
./scripts/startup/node2_startup_steps12.sh

# Node1
./scripts/startup/node1_startup_steps12.sh --download-yolo --run-validations
./scripts/startup/node1_startup_step13.sh
```

Run the Step 14 validation from Node1:

```bash
./scripts/startup/node1_startup_step14.sh --duration-sec 60
```

Manual Node2-style trigger endpoint:

```bash
curl -fsS -X POST http://192.168.29.20:8080/motion/events/node2   -H 'Content-Type: application/json'   -d '{
    "camera_id": "c922_node2_gate",
    "profile": "mjpeg_720p30",
    "duration_sec": 60,
    "device": "/dev/video0",
    "motion_score": 1.0,
    "motion_source": "node2",
    "requested_by": "node2_motion"
  }' | python3 -m json.tool
```

The response includes:

```text
/motion/streams/<session_id>/live.mp4
/motion/streams/<session_id>/preview.mp4
/capture/sessions/<session_id>
/capture/sessions/<session_id>/artifacts
```

LAN viewer:

```bash
vlc http://192.168.29.20:8080/motion/streams/<session_id>/live.mp4
```

After completion:

```bash
vlc http://192.168.29.20:8080/motion/streams/<session_id>/preview.mp4
```

See `docs/STEP14_MOTION_LIVE_MP4.md` for the full API and validation flow.

## Step 15: Node2 YOLO motion trigger for Node1-managed capture

Step 15 adds the first real Node2-side trigger path for the Step 14 live MP4 capture flow. In the stable Option A design, Node2 runs a local watcher that owns `/dev/video0` while idle, uses a cheap frame-difference gate, confirms interesting motion with the shared YOLO ONNX detector, releases the camera, and posts a motion event to Node1. Node1 remains the session authority and starts the bounded `timed_jpeg_udp` capture through the existing Node2 control agent.

```text
Node2 watcher -> /motion/events/node2 on Node1
Node1 CaptureSessionManager -> Node2 /stream/start transport=timed_jpeg_udp
Node1 dataset writer -> source JPEG frames + live.mp4 + preview.mp4 + manifest/report
Node2 watcher -> waits for terminal Node1 session status -> cooldown -> resumes watching
```

Static validation:

```bash
./scripts/validate_step15_node2_motion_trigger.sh --static-only
```

Synthetic end-to-end trigger validation from Node2 after Node1 and Node2 services are running:

```bash
./scripts/validate_step15_node2_motion_trigger.sh --synthetic-trigger
```

Manual one-shot real watcher run:

```bash
./scripts/node2/run_node2_motion_watcher.sh --one-shot
```

See `docs/STEP15_NODE2_YOLO_MOTION_TRIGGER.md` for the full state machine, environment variables, validation steps, and Option A limitations.

## Step 16: production-readiness baseline

Step 16 addresses the post-Step-15 production gaps: Node1 API authorization/RBAC, signed Node1↔Node2 local calls, Grafana/Prometheus hardening defaults, model registry/checksum/provider metadata, ONNX Runtime provider validation, trigger-to-capture-start latency metrics, storage retention/quota controls, multi-camera policy abstraction, local evidence indexing for future RAG, and FastAPI lifespan startup.

Key endpoints:

```text
GET  /security/runtime
GET  /models/registry
GET  /models/verify
GET  /inference/providers?requested=auto
GET  /cameras/runtime
GET  /storage/status
POST /storage/prune?dry_run=true
POST /index/build
GET  /capture/sessions/{session_id}/completeness
```

Validation:

```bash
./scripts/validate_step16_production_readiness.sh
```

The Step 16 test suite is deterministic even when your shell has sourced
`deploy/ai-camera.env`; the pytest fixture clears deployment auth/signing
variables before each test and individual tests set the values they need.

Design notes: `docs/STEP16_PRODUCTION_READINESS.md`.
