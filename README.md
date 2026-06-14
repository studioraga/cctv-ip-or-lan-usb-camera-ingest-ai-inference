# CCTV/IP or LAN USB Camera Ingest + AI Inference Platform

A **local-first AI CCTV / USB camera platform** validated on a two-node LAN. The current milestone streams a Logitech C922 camera from **Node2 Jetson Orin Nano** to **Node1 x86 workstation**, decodes frames through **GStreamer + OpenCV**, exposes FastAPI control services, records Prometheus metrics, and persists motion evidence into JSONL, SQLite, keyframes, and MP4 clips.

The system is intentionally local. Camera frames, events, clips, keyframes, SQLite metadata, policies, and future embeddings remain inside the LAN unless explicitly exported.

---

## 1. Validated topology

| Node | Validated host/IP | Role | Main services |
|---|---|---|---|
| Node1 | `sr-kaaldev` / `192.168.29.20` | Receiver, API gateway, event DB, evidence capture | `node1-ai-camera-api.service`, `node1-ai-camera-receiver.service` |
| Node2 | `shiva-vaisesika` / `192.168.29.188` | Jetson camera streamer and control agent | `node2-camera-control-agent.service` |

Default ports:

```text
Node2 -> Node1 RTP/JPEG:      UDP 5000
Node1 API gateway:            http://192.168.29.20:8080
Node1 receiver metrics:       http://192.168.29.20:9101/metrics
Node2 control agent:          http://192.168.29.188:8082
Node2 control metrics:        http://192.168.29.188:8082/metrics
```

Validated data path:

```text
Logitech C922 USB camera
  -> Node2 /dev/video0 through V4L2
  -> GStreamer MJPEG RTP sender
  -> UDP/RTP port 5000 over LAN
  -> Node1 GStreamer/OpenCV receiver
  -> BGR frames [720, 1280, 3]
  -> receiver FPS metrics
  -> motion events
  -> JSONL + SQLite + keyframe JPG + clip MP4
```

---

## 2. Current validation milestone

| Area | Status | Evidence |
|---|---:|---|
| Node1 API service | PASS | `/health` returns `node1_api_gateway`, policy version 2 |
| Node1 receiver service | PASS | active systemd service, UDP 5000 bound, metrics 9101 listening |
| Node1 OpenCV/GStreamer | PASS | `.venv` sees apt OpenCV `GStreamer: YES (1.24.1)` |
| Node2 control service | PASS | `/health` returns `node2_control_agent`, policy version 2 |
| Node2 camera mode | PASS | `/dev/video0`, MJPG 1280x720 at 30 FPS available |
| Manual GStreamer stream | PASS | RTP/JPEG caps negotiated and Node1 frames increased |
| API-controlled stream | PASS | Node1 POST to Node2 `/stream/start`, `/stream/status`, `/stream/stop` |
| Receiver metrics | PASS | `ai_camera_receiver_fps` around 14.9-15.1 FPS |
| Evidence logs | PASS | `results/node1/events.jsonl` records `receiver_fps` and `motion_detected` |
| SQLite events | PASS | latest `motion_detected` rows queryable from `data/events/ai_camera.db` |
| Clip/keyframe output | PASS | event records include `clip_path` and `keyframe_path` |

Final Step 9 gate:

```text
Node1 receiver readiness              PASS
Node2 camera mode MJPG 720p30         PASS
Node2 API endpoint discovery          PASS
GStreamer dry-run                     PASS
Manual streaming                      PASS
API-controlled streaming              PASS
Evidence DB/log check                 PASS
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
  node1/node1_receiver_agent.py          # Node1 RTP receiver + metrics + event capture
  node2/node2_streamer_controller.py     # Node2 GStreamer command builder/runner
services/
  common/                                # policy, migrations, DB, path security
  node1_api_gateway/                     # Node1 FastAPI API gateway
  node2_control_agent/                   # Node2 FastAPI camera control service
scripts/
  common/                                # deployment render/install/sync helpers
  ci/                                    # static and node-local validation scripts
  node1/                                 # Node1 dependency/venv/run helpers
  node2/                                 # Node2 dependency/venv/run helpers
  validate_step9_streaming.sh            # Node1-driven API stream validation
systemd/templates/                       # portable service templates
migrations/                              # SQLite migrations
configs/runtime/                         # generated runtime configs, not hand-edited
docs/                                    # architecture, deployment, CI, validation notes
```

Generated runtime artifacts such as `.venv`, `.venv.backup-*`, `results/`, SQLite DB/WAL/SHM files, clips, keyframes, `__pycache__`, and pyc files are excluded from clean source sync/archive outputs.

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
sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG \
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
RECREATE_VENV=1 scripts/node2/setup_node2_venv.sh
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
sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG \
  "$PWD/.venv/bin/python" scripts/common/install_systemd_units.py --role node2
sudo systemctl daemon-reload
sudo systemctl enable --now node2-camera-control-agent.service
```

Validate Node2:

```bash
curl -fsS http://192.168.29.188:8082/health | python3 -m json.tool
curl -fsS http://192.168.29.188:8082/openapi.json | jq '.paths | keys'
```

Note: `/stream/status`, `/stream/start`, and `/stream/stop` are policy-protected and should be called from trusted Node1. A 403 from Node2 itself is expected unless Node2 is also added to the trusted-control allow-list.

---

## 7. Step 9 API-controlled streaming validation

Run from Node1:

```bash
./scripts/validate_step9_streaming.sh
```

Manual equivalent:

```bash
curl -fsS -X POST http://192.168.29.188:8082/stream/start \
  -H 'Content-Type: application/json' \
  -d '{"camera_id":"c922_node2_gate","node1_ip":"192.168.29.20","port":5000,"device":"/dev/video0","profile":"mjpeg_720p30"}' | python3 -m json.tool

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

Evidence checks on Node1:

```bash
tail -n 20 results/node1/events.jsonl
sqlite3 data/events/ai_camera.db "
SELECT event_id, camera_id, event_type, ts, confidence
FROM events
ORDER BY ts DESC
LIMIT 10;
"
```

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Node1 receiver restart storm with `Failed to open GStreamer pipeline` | Node1 `.venv` OpenCV reports `GStreamer: NO` | Recreate Node1 venv with `RECREATE_VENV=1 scripts/node1/setup_node1_venv.sh` |
| `ModuleNotFoundError: services` in receiver | Receiver launched as script instead of module | Use generated systemd unit with `python -m agents.node1.node1_receiver_agent` |
| Node2 `/stream/status` returns 403 from Node2 shell | Policy trusts Node1 control IP | Run status from Node1 or update policy intentionally |
| Node2 stream exits rc=1 with `/dev/video0 busy` | Manual `gst-launch` or stale process owns camera | Stop manual sender; `ps -ef | grep gst-launch`; retry |
| Frames do not increase on Node1 | Node1 receiver down, wrong RTP port, firewall, or sender not running | Check systemd, `ss -lunp`, Node2 journal, and metrics |

---

## 9. Development and CI checks

```bash
./scripts/ci/validate_static.sh
source .venv/bin/activate
./scripts/ci/validate_node1_runtime.sh
./scripts/ci/validate_node2_runtime.sh
./scripts/common/prepare_deployment.sh node1
./scripts/common/prepare_deployment.sh node2
```

See also:

- `docs/ARCHITECTURE.md`
- `docs/VENV_SETUP.md`
- `docs/PORTABLE_DEPLOYMENT.md`
- `docs/CI_CD_VALIDATION_PLAN.md`
- `docs/NODE1_STEP7_VALIDATION_STATUS.md`
- `docs/STEP1_MIGRATIONS_POLICY_MEDIA_SECURITY.md`
- `docs/TASK1_IMPLEMENTATION_NOTES.md`
- `docs/GIT_COMMIT_MESSAGE_VALIDATION_MILESTONE.md`
