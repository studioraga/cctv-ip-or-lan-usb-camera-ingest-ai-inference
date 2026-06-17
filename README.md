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

Validated production stream path:

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

Validated Step 13 capture-session path:

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

## 2. Current validation milestone

| Area | Status | Evidence |
|---|---:|---|
| Node1 API service | PASS | `/health` returns `node1_api_gateway`, policy version 2 |
| Node1 receiver service | PASS | active systemd service, default `--transport rtp`, UDP 5000, metrics 9101 |
| Node1 OpenCV/GStreamer | PASS | `.venv` sees apt OpenCV `GStreamer: YES (1.24.1)` |
| Node2 control service | PASS | `/health` returns `node2_control_agent`, policy version 2 |
| Node2 camera mode | PASS | `/dev/video0`, MJPG 1280x720 at 30 FPS available |
| API-controlled RTP stream | PASS | Node1 starts/stops Node2 RTP sender and Node1 frames increase |
| Step 11 latency monitoring | PASS | bounded-slices metrics exported for `frame_gap_ms`, `capture_read_ms`, `capture_queue_wait_ms` |
| Step 12 E2E latency | PASS | `timed_jpeg_udp` exports frame IDs and sender-to-Node1 latency metrics |
| YOLO ONNX postprocess | PASS | generic YOLOv5/YOLOv8 decoder unit tests pass; real model smoke is optional |
| Step 13 capture sessions | PASS | UI/API capture writes source JPEG dataset and artifacts under `data/datasets/` |
| Prometheus stack | PASS | generated `configs/runtime/prometheus.yml` mounted into container and health endpoint is green |
| Grafana provisioning | PASS | dashboard `AI Camera / AI Camera Capture Session Demo` appears after provisioning path fix |

Recent live Step 13 evidence from Node1:

```text
UI capture session: cap_20260617_094247_c42c7f87
status: completed
requested duration: 30 sec
frames_written: 437
bytes_written: 87274343
dropped_frames: 0
avg e2e latency: ~18.19 ms
p95 e2e latency: ~18.64 ms
preview artifact: artifacts/preview.mp4

Automated validation session: cap_20260617_095226_d463178f
status: completed
frames_written: 137
[OK] Step 13 capture-session dataset validation completed
```

---

## 3. Critical runtime rule for Node1

Node1 receiver uses OpenCV `VideoCapture(..., cv2.CAP_GSTREAMER)`. Node1 `.venv` must therefore use apt/system OpenCV with GStreamer support.

Bad state found during validation:

```text
opencv: 4.13.0
GStreamer: NO
[ERROR] Failed to open GStreamer pipeline
```

Fixed state:

```text
python3 -m venv --system-site-packages .venv
opencv: 4.6.0
GStreamer: YES (1.24.1)
```

Do **not** install `opencv-python` or `opencv-contrib-python` into Node1 `.venv`.

---

## 4. Repository layout

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
  ci/                                    # static and node-local validation scripts
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

## 5. Node1 setup

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Edit `deploy/ai-camera.env` for Node1:

```text
AI_CAMERA_NODE_ROLE=node1
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
AI_CAMERA_PROFILE=mjpeg_720p30
AI_CAMERA_CAMERA_ID=c922_node2_gate
AI_CAMERA_NODE1_RTP_PORT=5000
AI_CAMERA_CAPTURE_UDP_PORT=5001
AI_CAMERA_DATASET_ROOT=data/datasets
AI_CAMERA_CAPTURE_MAX_DURATION_SEC=7200
AI_CAMERA_EVENT_LOG=results/node1/events.jsonl
```

Install dependencies and create Node1 `.venv`:

```bash
scripts/node1/install_node1_dependencies.sh
RECREATE_VENV=1 scripts/node1/setup_node1_venv.sh
source .venv/bin/activate
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

Expected: `GStreamer: YES`.

Prepare and install Node1 systemd units:

```bash
set -a; source deploy/ai-camera.env; set +a
export AI_CAMERA_REPO_ROOT="$PWD"
./scripts/common/prepare_deployment.sh node1
sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_CAPTURE_UDP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_TRANSPORT,AI_CAMERA_DATASET_ROOT,AI_CAMERA_CAPTURE_MAX_DURATION_SEC,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG,AI_CAMERA_LATENCY_THRESHOLD_MS,AI_CAMERA_LATENCY_WINDOW_SAMPLES \
  "$PWD/.venv/bin/python" scripts/common/install_systemd_units.py --role node1
sudo systemctl daemon-reload
sudo systemctl enable --now node1-ai-camera-api.service node1-ai-camera-receiver.service
```

Validate Node1:

```bash
systemctl status node1-ai-camera-api.service --no-pager --full
systemctl status node1-ai-camera-receiver.service --no-pager --full
curl -fsS http://192.168.29.20:8080/health | python3 -m json.tool
curl -fsS http://192.168.29.20:9101/metrics | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total' -A 2
sudo ss -lunp | grep ':5000'
```

---

## 6. Node2 setup

On Node2:

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Edit `deploy/ai-camera.env` for Node2:

```text
AI_CAMERA_NODE_ROLE=node2
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
AI_CAMERA_DEVICE=/dev/video0
AI_CAMERA_PROFILE=mjpeg_720p30
```

Install dependencies and create Node2 `.venv`:

```bash
scripts/node2/install_node2_dependencies.sh
PYTHONNOUSERSITE=1 RECREATE_VENV=1 scripts/node2/setup_node2_venv.sh
source .venv/bin/activate
```

Verify camera mode:

```bash
v4l2-ctl --device=/dev/video0 --list-formats-ext | grep -A8 -B2 '1280x720'
```

Expected under MJPG: `1280x720` with `0.033s (30.000 fps)`.

Prepare and install Node2 service:

```bash
set -a; source deploy/ai-camera.env; set +a
export AI_CAMERA_REPO_ROOT="$PWD"
./scripts/common/prepare_deployment.sh node2
sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_CAPTURE_UDP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG,PYTHONNOUSERSITE \
  "$PWD/.venv/bin/python" scripts/common/install_systemd_units.py --role node2
sudo systemctl daemon-reload
sudo systemctl enable --now node2-camera-control-agent.service
```

Validate Node2 from Node1:

```bash
curl -fsS http://192.168.29.188:8082/health | python3 -m json.tool
curl -fsS http://192.168.29.188:8082/stream/status | python3 -m json.tool
```

Note: `/stream/status`, `/stream/start`, and `/stream/stop` are policy-protected and should be called from trusted Node1. A 403 from Node2 itself is expected unless Node2 is also added to the trusted-control allow-list.

---

## 7. Production RTP stream validation

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
ai_camera_receiver_fps{camera_id="c922_node2_gate",profile="mjpeg_720p30"} ~15
ai_camera_frames_total{camera_id="c922_node2_gate",profile="mjpeg_720p30"} increasing
```

---

## 8. Step 11/12 latency and YOLO validation

Step 11 adds rolling bounded-slices stability monitoring for Node1 receiver timing:

```text
frame_gap_ms
capture_read_ms
capture_queue_wait_ms
```

Run:

```bash
./scripts/validate_step11_latency_monitoring.sh
```

Step 12 adds timestamped JPEG/UDP E2E correlation and YOLO ONNX postprocessing:

```bash
./scripts/validate_step12_e2e_latency.sh
./scripts/validate_step12_yolo_onnx.sh
```

The default production receiver remains:

```text
AI_CAMERA_TRANSPORT=rtp
```

Step 12/13 use `transport=timed_jpeg_udp` only when explicitly requested by validation scripts or capture sessions.

---

## 9. Step 13 Grafana capture-session demo

Validate Grafana/Prometheus provisioning:

```bash
./scripts/validate_step13_grafana_stack.sh
```

Start the Node1 stack:

```bash
./scripts/common/render_prometheus_config.sh
docker compose -f docker/docker-compose.node1.yml up -d
```

The compose file is under `docker/`, so relative mounts must be:

```yaml
../configs/runtime/prometheus.yml:/etc/prometheus/prometheus.yml:ro
./grafana/provisioning:/etc/grafana/provisioning:ro
./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

Health checks:

```bash
curl -fsS http://192.168.29.20:9090/-/healthy
curl -fsS http://192.168.29.20:3000/api/health | python3 -m json.tool
curl -fsS -u admin:admin 'http://192.168.29.20:3000/api/search?query=AI%20Camera' | python3 -m json.tool
```

Open:

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

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Node1 receiver restart storm with `Failed to open GStreamer pipeline` | Node1 `.venv` OpenCV reports `GStreamer: NO` | Recreate Node1 venv with `RECREATE_VENV=1 scripts/node1/setup_node1_venv.sh` |
| `ModuleNotFoundError: services` in receiver | Receiver launched as script instead of module | Use generated systemd unit with `python -m agents.node1.node1_receiver_agent` |
| Node2 `/stream/status` returns 403 from Node2 shell | Policy trusts Node1 control IP | Run status from Node1 or update policy intentionally |
| Node2 stream exits rc=1 with `/dev/video0 busy` | Manual `gst-launch`, timed sender, or stale process owns camera | Stop manual sender; check `ps -ef | grep -E 'gst-launch|node2_timed_jpeg_sender|ffmpeg'`; retry |
| Frames do not increase on Node1 | Node1 receiver down, wrong RTP/capture port, firewall, or sender not running | Check systemd, `ss -lunp`, Node2 journal, and metrics |
| Prometheus container fails to mount config | Compose path resolved relative to `docker/` | Use `../configs/runtime/prometheus.yml` in `docker/docker-compose.node1.yml` |
| Grafana is healthy but dashboard is missing | Provisioning paths resolved relative to `docker/` incorrectly | Use `./grafana/provisioning` and `./grafana/dashboards` in compose; restart with `--force-recreate` |
| Capture session stays at `running frames=0` | Node2 stream not sending to UDP 5001, camera busy, or firewall blocks capture UDP | Check Node2 status/journal, `AI_CAMERA_CAPTURE_UDP_PORT`, and firewall |

---

## 11. Development and CI checks

```bash
./scripts/ci/validate_static.sh
source .venv/bin/activate
python3 -m pytest -q
./scripts/ci/validate_node1_runtime.sh
./scripts/ci/validate_node2_runtime.sh
./scripts/common/prepare_deployment.sh node1
./scripts/common/prepare_deployment.sh node2
./scripts/validate_step11_latency_monitoring.sh
./scripts/validate_step12_e2e_latency.sh
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
- `docs/TASK1_IMPLEMENTATION_NOTES.md`
- `docs/GIT_COMMIT_MESSAGE_VALIDATION_MILESTONE.md`
