# CCTV/IP or LAN USB Camera Ingest + AI Inference Platform

A **local-first AI CCTV / USB camera platform** built from a validated two-node LAN camera streaming lab. This repository combines the original **AI Camera Node1/Node2 Agent Framework** documentation with the newer validated service-layer work.

The platform currently uses a **Logitech C922 Pro Stream Webcam** attached to **Node2 Jetson Orin Nano** and streams video over LAN to **Node1 x86 workstation** running **GStreamer + OpenCV + optional ONNX Runtime**. It now also includes FastAPI control services, Prometheus metrics, SQLite event indexing, motion-triggered keyframe/clip capture, and scaffolding for ONNX object detection, query, Qdrant, policy, mTLS, systemd, and Docker/Compose deployment.

The system is intentionally **LAN-local**. Camera frames, events, clips, keyframes, SQLite metadata, policies, and future embeddings remain inside the local network unless explicitly exported.

---

## 1. Validated deployment topology

| Node | Role | IP | Main responsibility |
|---|---|---:|---|
| Node1 | Receiver, API gateway, event DB, AI/event pipeline | `192.168.29.20` | Receives RTP frames, decodes with GStreamer/OpenCV, emits events, saves clips/keyframes, exposes API/metrics |
| Node2 | Jetson camera streamer and control agent | `192.168.29.188` | Captures Logitech C922 through V4L2 and streams RTP over UDP to Node1 |

Default transport and service ports:

```text
Camera transport:        UDP/RTP port 5000
Node1 API gateway:       http://192.168.29.20:8080
Node1 receiver metrics:  http://192.168.29.20:9101/metrics
Node2 control agent:     http://192.168.29.188:8082
Node2 control metrics:   http://192.168.29.188:8082/metrics
```

Validated data path:

```text
Logitech C922 USB camera
  -> Node2 Jetson Orin Nano
  -> /dev/video0 through V4L2
  -> GStreamer sender
  -> RTP over UDP port 5000
  -> Node1 receiver
  -> GStreamer depayload/decode
  -> OpenCV BGR frames
  -> display / FPS / metrics / JSONL / SQLite / keyframe / clip / optional ONNX inference
```

---

## 2. Validated milestone status

| Area | Status | Evidence / result |
|---|---:|---|
| Logitech C922 USB/V4L2 camera on Node2 | Validated | `/dev/video0` works as C922 capture node |
| Node2 GStreamer RTP/JPEG sender | Validated | `mjpeg_480p30`, `mjpeg_720p30`, `mjpeg_720p60`, `mjpeg_1080p30` |
| Node2 raw RTP debug sender | Validated after fix | `yuyv_640x480` uses `YUY2 -> videoconvert -> UYVY -> rtpvrawpay pt=96` |
| Node1 OpenCV/GStreamer receiver | Validated | Receives frames such as `frame=(720, 1280, 3)` |
| Node1 display/headless receiver modes | Validated | Display exits cleanly; headless exits through no-frame watchdog |
| Project-local Python `.venv` | Validated | Separate Node1/Node2 venvs; do not sync `.venv` across architectures |
| Node2 FastAPI control agent | Validated | `/health`, `/stream/profiles`, `/stream/start`, `/stream/stop`, `/stream/switch-profile` |
| Node1 FastAPI API gateway | Validated | `/health`, `/cameras`, `/node2/status`, and camera start/stop via Node1 API |
| Prometheus metrics | Validated initial | Node1 receiver metrics on `:9101`; Node2 control metrics on `:8082/metrics` |
| SQLite event schema | Validated | `cameras`, `clips`, `events` tables created and queryable |
| Motion event trigger | Validated | `motion_detected` rows inserted into SQLite |
| Keyframe capture | Validated | `data/keyframes/*.jpg` created for motion events |
| Clip capture | Validated | `data/clips/c922_node2_gate/YYYY-MM-DD/*.mp4` created and linked to events |
| Receiver lifecycle robustness | Validated after V2 fix | Threaded capture + no-frame watchdog exits after Node2 stream stops |

Next implementation targets:

1. ONNX object detection worker.
2. Object-triggered event/keyframe/clip capture using the same validated evidence chain.
3. Deterministic natural-language query endpoint validation.
4. Qdrant/vector search scaffold validation.
5. Policy enforcement, mTLS, and systemd/Docker deployment validation.

---

## 3. Architecture

```text
+-------------------------------+          RTP/UDP :5000          +-------------------------------------+
| Node2 Jetson Orin Nano        | ------------------------------> | Node1 Workstation                    |
| 192.168.29.188                |                                 | 192.168.29.20                        |
|                               |                                 |                                     |
| Logitech C922 USB Camera      |                                 | OpenCV/GStreamer receiver            |
| /dev/video0 via V4L2          |                                 | Motion/ONNX event pipeline           |
| GStreamer RTP sender          |                                 | SQLite event DB                      |
| FastAPI control agent :8082   | <----- REST control ---------- | FastAPI API gateway :8080            |
| tegrastats optional           |                                 | Prometheus receiver metrics :9101    |
+-------------------------------+                                 +-------------------------------------+
```

Validated USB camera path:

```text
C922 USB camera
  -> Node2 /dev/video0
  -> v4l2src
  -> image/jpeg or video/x-raw
  -> RTP payload
  -> udpsink host=192.168.29.20 port=5000
  -> Node1 udpsrc
  -> rtp depayload/decode
  -> OpenCV BGR frame
  -> display / metrics / DB / keyframe / clip / future ONNX inference
```

---

## 4. Supported stream profiles

| Profile | Node2 source caps | RTP payloader | Payload | Node1 receiver profile | Notes |
|---|---|---|---:|---|---|
| `mjpeg_480p30` | `image/jpeg,width=640,height=480,framerate=30/1` | `rtpjpegpay` | 26 | `mjpeg_480p30` | Low-bandwidth fallback/debug profile |
| `mjpeg_720p30` | `image/jpeg,width=1280,height=720,framerate=30/1` | `rtpjpegpay` | 26 | `mjpeg_720p30` | Recommended baseline profile |
| `mjpeg_720p60` | `image/jpeg,width=1280,height=720,framerate=60/1` | `rtpjpegpay` | 26 | `mjpeg_720p60` | High-FPS validation profile |
| `mjpeg_1080p30` | `image/jpeg,width=1920,height=1080,framerate=30/1` | `rtpjpegpay` | 26 | `mjpeg_1080p30` | High-resolution profile |
| `yuyv_640x480` | `video/x-raw,format=YUY2,width=640,height=480,framerate=30/1` | `rtpvrawpay` | 96 | `yuyv_640x480` | Raw debug profile; sender converts `YUY2 -> UYVY` before RTP |

Important Jetson note: the earlier `nvv4l2h264enc` path is not the default path. The validated Orin Nano environment did not expose a usable NVIDIA H.264 encoder element, so this repo uses MJPEG RTP and raw RTP debug profiles for the USB camera path.

Recommended active path:

```text
C922 MJPEG -> rtpjpegpay -> UDP -> rtpjpegdepay -> jpegdec -> OpenCV
```

---

## 5. Key implementation achievements

1. Logitech C922 was detected on Node2 as a USB UVC/V4L2 camera.
2. `/dev/video0` was confirmed as the active camera capture node.
3. C922 modes were validated through `v4l2-ctl` and FFmpeg format listing.
4. MJPEG streaming over RTP/UDP was selected as the stable LAN transport path.
5. The original H.264 hardware encoder path was intentionally avoided because `nvv4l2h264enc` was not present on the tested Jetson Orin Nano environment.
6. Node2 can stream `mjpeg_480p30`, `mjpeg_720p30`, `mjpeg_720p60`, `mjpeg_1080p30`, and `yuyv_640x480` profiles.
7. Node1 can receive MJPEG and YUYV/raw RTP profiles through OpenCV/GStreamer.
8. Node1 receiver runs inside a project-local Python `.venv` while preserving system OpenCV with GStreamer support.
9. Node2 controller runs inside a separate architecture-local Python `.venv`.
10. Node2 FastAPI control agent can start, stop, and switch streams remotely.
11. Node1 FastAPI API gateway can control Node2 and expose cameras/events/query/metrics.
12. Node1 event logging writes JSONL telemetry under `results/node1/`.
13. Node2 optional `tegrastats` logging writes thermal/power/system statistics under `results/node2/`.
14. SQLite `cameras`, `clips`, and `events` schema is initialized and queryable.
15. Motion events create database rows, keyframes, and MP4 clips.
16. Node1 threaded receiver fix prevents OpenCV `cap.read()` hangs after stream stop.
17. A C++ OpenCV/GStreamer probe is included for native receiver validation.
18. Policy, config, architecture notes, CI/CD validation notes, and repo sync scripts are included for GitHub-ready project organization.

---

## 6. Python environment rules

Use one source repository on both nodes, but create a separate `.venv` on each node.

Do **not** copy or sync `.venv` between Node1 and Node2.

Reason:

```text
Node1 = x86_64 Ubuntu workstation
Node2 = aarch64 Jetson Orin Nano
```

Python native wheels, OpenCV bindings, ONNX Runtime packages, and linked libraries are architecture-specific.

Correct pattern:

```text
Sync source code, scripts, configs, requirements.
Recreate .venv separately on each node.
Exclude .venv, __pycache__, results, DBs, keyframes, clips, and large media files from rsync/Git.
```

Node1 must preserve system OpenCV with GStreamer support. The Node1 setup uses `--system-site-packages` so the venv can see apt-installed `python3-opencv`.

Validate on Node1:

```bash
source .venv/bin/activate
python - << 'PY'
import cv2
print('cv2 version:', cv2.__version__)
for line in cv2.getBuildInformation().splitlines():
    if 'GStreamer' in line:
        print(line)
PY
```

Expected:

```text
GStreamer: YES
```

Validate ONNX Runtime:

```bash
python - << 'PY'
import onnxruntime as ort
print('onnxruntime:', ort.__version__)
print('providers:', ort.get_available_providers())
PY
```

---

## 7. Repository layout

```text
.
├── README.md
├── VALIDATION.md
├── TASK1_IMPLEMENTATION_SUMMARY.md
├── LICENSE
├── .gitignore
├── requirements-node1.txt
├── requirements-node2.txt
├── agents/
│   ├── common/
│   │   └── telemetry.py
│   ├── node1/
│   │   ├── node1_receiver_agent.py
│   │   └── node1_receiver_agent.py.bak
│   └── node2/
│       ├── node2_streamer_controller.py
│       └── node2_streamer_controller.py.back
├── services/
│   ├── common/
│   │   ├── event_db.py
│   │   └── policy.py
│   ├── node1_api_gateway/
│   │   ├── app.py
│   │   └── schemas.py
│   ├── node1_query_engine/
│   │   └── nl_parser.py
│   ├── node1_inference_worker/
│   │   ├── worker.py
│   │   └── detectors/
│   │       ├── motion.py
│   │       └── yolo_onnx.py
│   ├── node1_event_indexer/
│   │   └── qdrant_store.py
│   └── node2_control_agent/
│       ├── app.py
│       └── streamer_service.py
├── scripts/
│   ├── common/
│   │   └── sync_repo_to_node2.sh
│   ├── ci/
│   │   ├── validate_static.sh
│   │   ├── validate_node1_runtime.sh
│   │   └── validate_node2_runtime.sh
│   ├── node1/
│   │   ├── install_node1_dependencies.sh
│   │   ├── setup_node1_venv.sh
│   │   ├── run_node1_receiver_agent.sh
│   │   ├── run_node1_api_gateway.sh
│   │   ├── init_event_db.sh
│   │   ├── 01_opencv_install_node1.sh
│   │   ├── node1_reciever_mjpeg_720p30.sh
│   │   ├── node1_receiver_fps_only.py
│   │   ├── node1_receiver_display.py
│   │   └── node1_receiver_OpenCV_ai_orchestration.py
│   └── node2/
│       ├── install_node2_dependencies.sh
│       ├── setup_node2_venv.sh
│       ├── run_node2_control_agent.sh
│       ├── run_node2_streamer_controller.sh
│       ├── node2_sender_mjpeg_480p30.sh
│       ├── node2_sender_mjpeg_720p30.sh
│       ├── node2_sender_mjpeg_720p60.sh
│       └── node2_sender_720p30.sh
├── configs/
│   ├── cameras.yaml
│   ├── nodes.yaml
│   ├── runtime_profiles.yaml
│   ├── retention.yaml
│   └── zones.yaml
├── policies/
│   └── security_policy.yaml
├── security/
│   └── scripts/
│       ├── create_local_ca.sh
│       └── issue_node_cert.sh
├── systemd/
│   ├── node1-ai-camera-api.service
│   ├── node1-ai-camera-receiver.service
│   └── node2-camera-control-agent.service
├── docker/
│   ├── docker-compose.node1.yml
│   └── prometheus.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── VENV_SETUP.md
│   ├── TASK1_IMPLEMENTATION_NOTES.md
│   ├── CI_CD_VALIDATION_PLAN.md
│   └── GIT_COMMIT_MESSAGE_VALIDATION_MILESTONE.md
├── node1_receiver/
│   ├── 01_opencv_install_node1.sh
│   ├── node1_reciever_mjpeg_720p30.sh
│   ├── node1_receiver_fps_only.py
│   ├── node1_receiver_display.py
│   └── node1_receiver_OpenCV_ai_orchestration.py
├── cpp/
│   └── node1_frame_probe/
│       ├── CMakeLists.txt
│       └── node1_frame_probe.cpp
├── tools/
│   └── parse_tegrastats.py
└── results/
    ├── node1/
    └── node2/
```

---

## 8. Main files

| File | Purpose |
|---|---|
| `agents/node1/node1_receiver_agent.py` | Main Node1 threaded receiver agent with MJPEG/YUYV profiles, display, FPS, metrics, JSONL, SQLite, motion event, keyframe/clip, optional ONNX hook |
| `agents/node2/node2_streamer_controller.py` | Main Node2 Python streamer controller that launches GStreamer sender pipelines |
| `services/node2_control_agent/app.py` | Node2 FastAPI control service for start/stop/profile switch |
| `services/node1_api_gateway/app.py` | Node1 FastAPI API gateway for cameras, control, events, query, clips, metrics |
| `services/common/event_db.py` | SQLite event/clip/camera DB helper |
| `services/node1_query_engine/nl_parser.py` | Deterministic query parser scaffold |
| `services/node1_event_indexer/qdrant_store.py` | Lazy Qdrant scaffold |
| `scripts/node1/setup_node1_venv.sh` | Creates Node1 `.venv` with `--system-site-packages` and installs Node1 Python requirements |
| `scripts/node2/setup_node2_venv.sh` | Creates Node2 `.venv` and installs Node2 Python requirements |
| `scripts/common/sync_repo_to_node2.sh` | Rsync helper that excludes `.venv`, caches, and results |
| `cpp/node1_frame_probe/` | C++ OpenCV/GStreamer receiver probe |
| `tools/parse_tegrastats.py` | Parses Node2 `tegrastats` logs |
| `policies/security_policy.yaml` | Local LAN policy reference for UDP/5000 camera traffic and profile controls |
| `VALIDATION.md` | Incremental validation runbook for reproducing this milestone |
| `docs/CI_CD_VALIDATION_PLAN.md` | CI/CD strategy for static, node-local, and hardware-in-the-loop validation |

---

## 9. Prerequisites

### 9.1 Node1 receiver machine

Tested role: x86 workstation receiver.

Required system packages:

```bash
sudo apt update
sudo apt install -y   python3-full python3-venv python3-pip python3-opencv python3-numpy   ffmpeg sqlite3   gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good   gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav   build-essential cmake pkg-config libopencv-dev   ufw iproute2 net-tools htop
```

The key requirement is **OpenCV with GStreamer support**. The project expects system `python3-opencv` to provide `cv2` with `GStreamer: YES`.

Avoid installing pip `opencv-python` for this project unless you know your wheel has GStreamer enabled. Many pip OpenCV wheels do not include GStreamer support.

### 9.2 Node2 streamer machine

Tested role: Jetson Orin Nano camera streamer.

Required system packages:

```bash
sudo apt update
sudo apt install -y   v4l-utils ffmpeg   gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good   gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav   python3-full python3-venv python3-pip htop iproute2 net-tools
```

Node2 streams through GStreamer; Python only controls the selected profile and optional `tegrastats` logging.

---

## 10. Node1 setup

```bash
cd ~/dev/11.node1_cam_reciver/tt/Task1/cctv-ip-or-lan-usb-camera-ingest-ai-inference-main
chmod +x scripts/node1/install_node1_dependencies.sh
./scripts/node1/install_node1_dependencies.sh
chmod +x scripts/node1/setup_node1_venv.sh
./scripts/node1/setup_node1_venv.sh
source .venv/bin/activate
```

Validate environment:

```bash
which python
python --version

python - << 'PY'
import cv2
print("cv2 version:", cv2.__version__)
for line in cv2.getBuildInformation().splitlines():
    if "GStreamer" in line:
        print(line)
PY

python - << 'PY'
import onnxruntime as ort
print("onnxruntime:", ort.__version__)
print("providers:", ort.get_available_providers())
PY
```

Validate receiver syntax:

```bash
python -m py_compile agents/node1/node1_receiver_agent.py
```

Initialize event DB:

```bash
./scripts/node1/init_event_db.sh
```

---

## 11. Node2 setup

```bash
cd ~/dev/ai-system/tt/Task1/cctv-ip-or-lan-usb-camera-ingest-ai-inference-main
chmod +x scripts/node2/setup_node2_venv.sh
./scripts/node2/setup_node2_venv.sh
source .venv/bin/activate
```

Validate camera detection:

```bash
lsusb
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Expected device mapping:

```text
C922 Pro Stream Webcam
  /dev/video0
  /dev/video1
  /dev/media1
```

Validate GStreamer elements:

```bash
gst-launch-1.0 --version
gst-inspect-1.0 v4l2src
gst-inspect-1.0 rtpjpegpay
gst-inspect-1.0 rtpvrawpay
```

Validate streamer syntax:

```bash
python -m py_compile agents/node2/node2_streamer_controller.py
```

---

## 12. Manual validated run flow

### Terminal 1: Node2 control agent

Run this first on Node2:

```bash
cd ~/dev/ai-system/tt/Task1/cctv-ip-or-lan-usb-camera-ingest-ai-inference-main
source .venv/bin/activate
./scripts/node2/run_node2_control_agent.sh
```

Expected:

```text
Uvicorn running on http://192.168.29.188:8082
```

### Terminal 2: Node1 receiver

Headless service-style receiver:

```bash
cd ~/dev/11.node1_cam_reciver/tt/Task1/cctv-ip-or-lan-usb-camera-ingest-ai-inference-main
source .venv/bin/activate

python agents/node1/node1_receiver_agent.py   --profile mjpeg_720p30   --port 5000   --camera-id c922_node2_gate   --db-path data/events/ai_camera.db   --metrics   --metrics-port 9101   --motion-events   --no-frame-timeout-sec 10   --startup-timeout-sec 30   --event-log results/node1/events.jsonl
```

Display receiver:

```bash
python agents/node1/node1_receiver_agent.py   --profile mjpeg_720p30   --port 5000   --camera-id c922_node2_gate   --db-path data/events/ai_camera.db   --metrics   --metrics-port 9101   --motion-events   --display   --no-frame-timeout-sec 10   --startup-timeout-sec 30   --event-log results/node1/events.jsonl
```

Expected Node1 output while stream runs:

```text
[INFO] profile=mjpeg_720p30, FPS=..., frame=(720, 1280, 3), infer_ms=None
[EVENT] motion_detected event_id=... keyframe=data/keyframes/...jpg clip=data/clips/...mp4
```

Expected Node1 output after stream stop with V2 threaded receiver:

```text
[WARN] No frame available; consecutive_timeouts=...
[ERROR] No frames received for 10.0s; exiting receiver
[INFO] Releasing receiver resources...
[INFO] Receiver stopped. frames_total=..., exit_code=3
```

### Terminal 3: start/stop Node2 stream

Start:

```bash
curl -X POST http://192.168.29.188:8082/stream/start   -H 'Content-Type: application/json'   -d '{
    "node1_ip": "192.168.29.20",
    "port": 5000,
    "profile": "mjpeg_720p30",
    "device": "/dev/video0"
  }'
```

Stop:

```bash
curl -X POST http://192.168.29.188:8082/stream/stop
```

---

## 13. Node2 control agent API

Run:

```bash
./scripts/node2/run_node2_control_agent.sh
```

Validate:

```bash
curl http://192.168.29.188:8082/health
curl http://192.168.29.188:8082/stream/profiles
curl http://192.168.29.188:8082/stream/status
```

Start stream directly through Node2 API:

```bash
curl -X POST http://192.168.29.188:8082/stream/start   -H 'Content-Type: application/json'   -d '{"node1_ip":"192.168.29.20","port":5000,"profile":"mjpeg_720p30","device":"/dev/video0"}'
```

Switch profile:

```bash
curl -X POST http://192.168.29.188:8082/stream/switch-profile   -H 'Content-Type: application/json'   -d '{"node1_ip":"192.168.29.20","port":5000,"profile":"mjpeg_480p30","device":"/dev/video0"}'
```

Stop:

```bash
curl -X POST http://192.168.29.188:8082/stream/stop
```

---

## 14. Node1 API gateway

Start:

```bash
cd ~/dev/11.node1_cam_reciver/tt/Task1/cctv-ip-or-lan-usb-camera-ingest-ai-inference-main
source .venv/bin/activate
./scripts/node1/run_node1_api_gateway.sh
```

Validate:

```bash
curl http://192.168.29.20:8080/health
curl http://192.168.29.20:8080/cameras
curl http://192.168.29.20:8080/node2/status
```

Start Node2 stream through Node1 API:

```bash
curl -X POST http://192.168.29.20:8080/cameras/c922_node2_gate/start   -H 'Content-Type: application/json'   -d '{"profile":"mjpeg_720p30"}'
```

Stop:

```bash
curl -X POST http://192.168.29.20:8080/cameras/c922_node2_gate/stop
```

---

## 15. Running all stream profiles

### 15.1 MJPEG 480p30

Node1:

```bash
python agents/node1/node1_receiver_agent.py   --profile mjpeg_480p30   --port 5000   --buffer-size 8388608   --display   --event-log results/node1/mjpeg_480p30_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py   --node1-ip 192.168.29.20   --profile mjpeg_480p30   --tegrastats
```

Or through Node2 control agent:

```bash
curl -X POST http://192.168.29.188:8082/stream/start   -H 'Content-Type: application/json'   -d '{"node1_ip":"192.168.29.20","port":5000,"profile":"mjpeg_480p30","device":"/dev/video0"}'
```

### 15.2 MJPEG 720p30

Node1:

```bash
python agents/node1/node1_receiver_agent.py   --profile mjpeg_720p30   --port 5000   --buffer-size 8388608   --display   --event-log results/node1/mjpeg_720p30_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py   --node1-ip 192.168.29.20   --profile mjpeg_720p30   --tegrastats
```

### 15.3 MJPEG 720p60

Node1:

```bash
python agents/node1/node1_receiver_agent.py   --profile mjpeg_720p60   --port 5000   --buffer-size 8388608   --display   --event-log results/node1/mjpeg_720p60_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py   --node1-ip 192.168.29.20   --profile mjpeg_720p60   --tegrastats
```

### 15.4 MJPEG 1080p30

Node1:

```bash
python agents/node1/node1_receiver_agent.py   --profile mjpeg_1080p30   --port 5000   --buffer-size 16777216   --jitterbuffer   --jitter-latency-ms 80   --display   --event-log results/node1/mjpeg_1080p30_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py   --node1-ip 192.168.29.20   --profile mjpeg_1080p30   --tegrastats
```

### 15.5 YUYV 640x480 raw RTP

This mode is useful as a low-resolution raw-video debug path.

Node2 captures C922 as `YUY2`, converts it to `UYVY`, and sends raw RTP video:

```text
v4l2src -> video/x-raw,format=YUY2 -> videoconvert -> video/x-raw,format=UYVY -> rtpvrawpay pt=96 -> UDP
```

Node1:

```bash
python agents/node1/node1_receiver_agent.py   --profile yuyv_640x480   --port 5000   --buffer-size 8388608   --display   --event-log results/node1/yuyv_640x480_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py   --node1-ip 192.168.29.20   --profile yuyv_640x480   --tegrastats
```

The `videoconvert -> UYVY` step is important. Directly linking `YUY2 -> rtpvrawpay` caused the earlier GStreamer error:

```text
could not link queue0 to rtpvrawpay0
```

---

## 16. Direct GStreamer validation commands

### 16.1 Node2 local camera FPS test

Run on Node2:

```bash
gst-launch-1.0 -v   v4l2src device=/dev/video0 io-mode=2 do-timestamp=true !   image/jpeg,width=1280,height=720,framerate=30/1 !   queue leaky=downstream max-size-buffers=2 !   fpsdisplaysink video-sink=fakesink text-overlay=false sync=false
```

### 16.2 Node1 pure GStreamer MJPEG receiver

Run on Node1 before starting Node2 sender:

```bash
gst-launch-1.0 -v   udpsrc port=5000 buffer-size=8388608   caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" !   queue leaky=downstream max-size-buffers=4 !   rtpjpegdepay !   jpegdec !   videoconvert !   fpsdisplaysink video-sink=fakesink text-overlay=false sync=false
```

### 16.3 Node1 pure GStreamer YUYV/raw receiver

```bash
gst-launch-1.0 -v   udpsrc port=5000 buffer-size=8388608   caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=RAW,payload=96,sampling=YCbCr-4:2:2,depth=(string)8,width=(string)640,height=(string)480,colorimetry=(string)BT601-5,a-framerate=(string)30.000000" !   queue leaky=downstream max-size-buffers=4 !   rtpvrawdepay !   videoconvert !   fpsdisplaysink video-sink=fakesink text-overlay=false sync=false
```

### 16.4 Node2 direct YUYV sender

```bash
gst-launch-1.0 -v -e   v4l2src device=/dev/video0 io-mode=2 do-timestamp=true !   video/x-raw,format=YUY2,width=640,height=480,framerate=30/1 !   videoconvert !   video/x-raw,format=UYVY !   queue leaky=downstream max-size-buffers=2 !   rtpvrawpay pt=96 !   udpsink host=192.168.29.20 port=5000 sync=false async=false
```

---

## 17. Metrics validation

Node1 receiver metrics:

```bash
curl http://192.168.29.20:9101/metrics | grep ai_camera
```

Expected metric families include:

```text
ai_camera_receiver_fps
ai_camera_frames_total
ai_camera_decode_failures_total
ai_camera_receiver_last_frame_age_seconds
ai_camera_inference_latency_ms
ai_camera_events_total
```

Node2 control metrics:

```bash
curl http://192.168.29.188:8082/metrics | grep ai_camera
```

Expected metric families include:

```text
ai_camera_stream_running
ai_camera_stream_starts_total
ai_camera_stream_stops_total
ai_camera_node2_control_errors_total
```

Node1 API gateway metrics:

```bash
curl http://192.168.29.20:8080/metrics | grep ai_camera
```

---

## 18. SQLite event and clip validation

Initialize DB:

```bash
./scripts/node1/init_event_db.sh
```

Check tables:

```bash
sqlite3 data/events/ai_camera.db ".tables"
```

Expected:

```text
cameras  clips  events
```

Recent events:

```bash
sqlite3 data/events/ai_camera.db   "select event_id,event_type,label,confidence,clip_id,ts from events order by ts desc limit 10;"
```

Recent clips:

```bash
sqlite3 data/events/ai_camera.db   "select clip_id,camera_id,path,keyframe_path,duration_sec from clips order by created_at desc limit 10;"
```

Event-to-clip join:

```bash
sqlite3 data/events/ai_camera.db "
select
  e.event_id,
  e.event_type,
  e.label,
  e.confidence,
  e.ts,
  c.path,
  c.keyframe_path,
  c.duration_sec
from events e
left join clips c on e.clip_id = c.clip_id
order by e.ts desc
limit 10;"
```

Filesystem evidence:

```bash
ls -lh data/keyframes | tail
find data/clips -type f -name "*.mp4" -printf "%p %s bytes
" | tail
```

The currently validated motion event chain is:

```text
motion_detected -> events row -> clip_id -> clips row -> keyframe_path -> .jpg file -> clip path -> .mp4 file
```

Example validated row shape:

```text
evt_... | motion_detected | motion | 1.0 | clip_evt_... | 2026-06-09T...
```

---

## 19. ONNX Runtime inference hook on Node1

The main receiver agent supports an optional generic model path:

```bash
python agents/node1/node1_receiver_agent.py   --profile mjpeg_720p30   --port 5000   --display   --model models/example.onnx   --event-log results/node1/onnx_events.jsonl
```

The current generic preprocessing in `OptionalOnnxModel.infer()` is intentionally simple:

```text
BGR frame -> resize 224x224 -> RGB -> float32 / 255 -> CHW -> NCHW -> ONNX Runtime
```

For a real model, update the preprocessing to match the model’s exact input shape, normalization, channel order, and output decoding.

Next ONNX object detection target:

```text
person detected by ONNX model
  -> event_type=person_detected
  -> label=person
  -> confidence=model confidence
  -> bbox_json=[x1,y1,x2,y2]
  -> keyframe saved
  -> clip saved
  -> clips row inserted
  -> events row inserted
  -> /events and /query can retrieve it
```

Node1 `requirements-node1.txt` includes:

```text
numpy>=1.23,<2.0
onnxruntime>=1.17
PyYAML>=6.0
prometheus-client>=0.20
```

---

## 20. Deterministic query endpoint

The deterministic query parser is an initial scaffold. It supports intent extraction for terms such as:

```text
summarize, summary, person, someone, who, vehicle, car, bike, motion, activity, gate, red shirt, after closing, after hours
```

API example:

```bash
curl -X POST http://192.168.29.20:8080/query   -H 'Content-Type: application/json'   -d '{
    "question": "summarize activity near the gate",
    "camera_id": "c922_node2_gate"
  }'
```

The current parser maps “activity” to `motion_detected`, so this is immediately testable against the validated motion events.

---

## 21. Event logs and telemetry

Node1 writes JSONL events such as:

```json
{"event": "receiver_started", "profile": "mjpeg_720p30", "port": 5000}
{"event": "receiver_fps", "profile": "mjpeg_720p30", "fps": 28.7, "frame_shape": [720, 1280, 3]}
{"event": "motion_detected", "event_id": "evt_...", "camera_id": "c922_node2_gate"}
{"event": "receiver_stopped", "profile": "mjpeg_720p30", "frames_total": 1000}
```

Default event log location:

```text
results/node1/events.jsonl
```

Node2 can collect `tegrastats` with:

```bash
python agents/node2/node2_streamer_controller.py   --node1-ip 192.168.29.20   --profile mjpeg_720p30   --tegrastats   --tegrastats-log results/node2/camera_stream_tegrastats.log
```

Parse `tegrastats` output:

```bash
python tools/parse_tegrastats.py results/node2/camera_stream_tegrastats.log
```

---

## 22. C++ receiver probe

A native C++ OpenCV/GStreamer receiver probe is included under:

```text
cpp/node1_frame_probe/
```

Build on Node1:

```bash
cd cpp/node1_frame_probe
mkdir -p build
cd build
cmake ..
make -j"$(nproc)"
```

Run:

```bash
./node1_frame_probe 5000
```

This probe currently targets the MJPEG/RTP payload-26 receiver path.

---

## 23. Source sync from Node1 to Node2

From the source machine:

```bash
cd ~/dev/11.node1_cam_reciver/tt/Task1/cctv-ip-or-lan-usb-camera-ingest-ai-inference-main

NODE2_USER=srrmk NODE2_IP=192.168.29.188 REMOTE_DIR=~/dev/ai-system/tt/Task1/cctv-ip-or-lan-usb-camera-ingest-ai-inference-main ./scripts/common/sync_repo_to_node2.sh
```

The sync script excludes:

```text
.git/
.venv/
__pycache__/
*.pyc
results/
```

This keeps source synchronized while preserving each node’s local virtual environment and runtime logs.

---

## 24. Network and firewall checklist

Node1 must accept UDP port 5000 from Node2.

Basic connectivity check:

```bash
ping 192.168.29.188   # from Node1
ping 192.168.29.20    # from Node2
```

Optional Node1 firewall rule:

```bash
sudo ufw allow from 192.168.29.188 to any port 5000 proto udp
```

Node2 control API access from Node1:

```bash
sudo ufw allow from 192.168.29.20 to any port 8082 proto tcp
```

Node1 API and metrics access on the LAN as needed:

```bash
sudo ufw allow 8080/tcp
sudo ufw allow 9101/tcp
```

The policy artifact is stored at:

```text
policies/security_policy.yaml
```

It documents the intended rule:

```text
Allow Node2 192.168.29.188 -> Node1 192.168.29.20 UDP/5000
Deny untrusted camera sources
Restrict runtime profile switching
Require metrics/event logs/tegrastats
```

---

## 25. Performance and optimization notes

### 25.1 UDP socket buffers

For higher resolution or higher FPS, increase Node1 UDP buffers:

```bash
sudo sysctl -w net.core.rmem_max=33554432
sudo sysctl -w net.core.rmem_default=8388608
sudo sysctl -w net.core.wmem_max=33554432
sudo sysctl -w net.core.wmem_default=8388608
```

Make persistent:

```bash
sudo tee /etc/sysctl.d/99-camera-stream.conf > /dev/null << 'EOF_SYSCTL'
net.core.rmem_max=33554432
net.core.rmem_default=8388608
net.core.wmem_max=33554432
net.core.wmem_default=8388608
EOF_SYSCTL

sudo sysctl --system
```

### 25.2 Receiver buffer size

Use larger receiver buffers for 1080p:

```bash
--buffer-size 16777216
```

### 25.3 Jitter buffer

For 1080p or unstable LAN conditions:

```bash
--jitterbuffer --jitter-latency-ms 80
```

### 25.4 CPU pinning on Node2

The Node2 sender uses:

```bash
taskset -c 0-3
```

This gives repeatable CPU placement for camera streaming tests.

### 25.5 Jetson monitoring

Run with:

```bash
--tegrastats
```

or manually:

```bash
sudo tegrastats
```

### 25.6 Jetson clock mode

For repeatable benchmarks, use Jetson performance mode carefully:

```bash
sudo nvpmodel -q
sudo jetson_clocks
```

Use this only when you understand the power and thermal impact.

### 25.7 FPS behavior

Node2 advertises `mjpeg_720p30` as 30 FPS. Node1 commonly reports around 15 FPS with display/motion/event processing. This is acceptable for the current event pipeline because:

```text
appsink drop=true sync=false max-buffers=1
```

favors low-latency freshness over processing every frame. For pure FPS analysis, compare against a GStreamer-only receiver.

---

## 26. Known issues and troubleshooting

### 26.1 Headless receiver hang fixed

Earlier OpenCV `cap.read()` could block when Node2 stream stopped. The current receiver uses a daemon capture thread and main-loop watchdog controls:

```text
--no-frame-timeout-sec
--startup-timeout-sec
--exit-on-no-frames / --no-exit-on-no-frames
```

This was validated: after Node2 `/stream/stop`, Node1 exits after the configured no-frame timeout instead of requiring `kill -9`.

### 26.2 Non-blocking GStreamer cleanup warning

During shutdown, OpenCV/GStreamer may print:

```text
GStreamer-CRITICAL **: gst_mini_object_unref: assertion ... failed
```

The process still releases resources and exits. Treat this as a non-blocking cleanup warning for now. A future improvement is to replace OpenCV `VideoCapture` with native Python GStreamer `appsink` ownership via `gi.repository.Gst`.

### 26.3 Node1 receives frames but no OpenCV window appears

Make sure you passed `--display`:

```bash
python agents/node1/node1_receiver_agent.py --profile mjpeg_720p30 --display
```

Check GUI environment:

```bash
echo $DISPLAY
```

If empty, run from Node1 desktop terminal or use SSH X forwarding:

```bash
ssh -X rmk@192.168.29.20
```

Test OpenCV GUI independently:

```bash
python - << 'PY'
import cv2
import numpy as np
img = np.zeros((480, 640, 3), dtype=np.uint8)
cv2.putText(img, "OpenCV GUI Test", (80, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255,255,255), 2)
cv2.imshow("GUI test", img)
cv2.waitKey(5000)
cv2.destroyAllWindows()
PY
```

### 26.4 `ffplay` says no video device or DISPLAY is not set

That is a GUI/session problem, not necessarily a camera problem. Use headless recording or GStreamer fakesink tests.

### 26.5 `cv2.VideoCapture(..., cv2.CAP_GSTREAMER)` fails

Check that OpenCV has GStreamer support:

```bash
python - << 'PY'
import cv2
for line in cv2.getBuildInformation().splitlines():
    if "GStreamer" in line:
        print(line)
PY
```

Expected:

```text
GStreamer: YES
```

If not, install apt OpenCV and recreate venv with `--system-site-packages`.

### 26.6 Low FPS on Node1

Test in layers:

1. Node2 local camera FPS with `fpsdisplaysink`.
2. Node1 pure GStreamer receiver with `fpsdisplaysink video-sink=fakesink`.
3. Node1 Python/OpenCV receiver.
4. Node1 Python/OpenCV display receiver.

If pure GStreamer is fast but Python is slow, the bottleneck is the Python/OpenCV loop or display/motion/DB/clip path. If pure GStreamer is also slow, check LAN packet loss, socket buffers, camera mode, USB link, and system load.

### 26.7 YUYV sender fails with `could not link queue0 to rtpvrawpay0`

Use the corrected path:

```text
YUY2 -> videoconvert -> UYVY -> queue -> rtpvrawpay
```

The active Node2 controller already uses this corrected path.

### 26.8 Verify generated Node2 commands

```bash
python3 - << 'PY'
from agents.node2.node2_streamer_controller import build_gstreamer_command

for profile in [
    "mjpeg_480p30",
    "mjpeg_720p30",
    "mjpeg_720p60",
    "mjpeg_1080p30",
    "yuyv_640x480",
]:
    cmd = build_gstreamer_command(profile, "192.168.29.20", 5000, "/dev/video0")
    print("\nPROFILE:", profile)
    print(" ".join(cmd))
PY
```

### 26.9 Validate Python syntax

```bash
python3 -m py_compile agents/node1/node1_receiver_agent.py
python3 -m py_compile agents/node2/node2_streamer_controller.py
python3 -m py_compile agents/common/telemetry.py
python3 -m py_compile tools/parse_tegrastats.py
```

---

## 27. CI/CD validation overview

Initial scripts are under:

```text
scripts/ci/
```

Recommended local runs:

```bash
./scripts/ci/validate_static.sh
./scripts/ci/validate_node1_runtime.sh
./scripts/ci/validate_node2_runtime.sh
```

Static CI validates:

```text
Python syntax
YAML parsing
shell script syntax
Node2 GStreamer command generation
SQLite schema initialization
deterministic query parser smoke checks
service module imports
```

Hardware-in-the-loop validation should remain manual or run from self-hosted runners on Node1/Node2.

See:

```text
docs/CI_CD_VALIDATION_PLAN.md
```

---

## 28. GitHub preparation checklist

Before pushing:

```bash
find . -type d -name __pycache__ -prune -exec rm -rf {} +
find . -type f -name '*.pyc' -delete
```

Recommended `.gitignore` entries:

```gitignore
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/

# runtime outputs
results/**/*.jsonl
results/**/*.log
data/events/*.db
data/keyframes/*.jpg
data/clips/**/*.mp4

# media/model artifacts
*.mp4
*.mkv
*.mjpg
*.onnx

# build/editor
build/
.DS_Store
.vscode/
.idea/
```

Decide whether to commit sample logs under `results/`. For a clean public repository, it is usually better to commit a small `results/README.md` or `.gitkeep`, but not large generated logs.

If runtime artifacts were already staged:

```bash
git rm -r --cached __pycache__ agents/node1/__pycache__ services/**/__pycache__ || true
git rm -r --cached data/events/*.db data/clips data/keyframes results || true
git add data/clips/.gitkeep data/keyframes/.gitkeep data/events/.gitkeep results/node1/.gitkeep results/node2/.gitkeep
```

---

## 29. Suggested incremental commit message

```text
Validate Node1/Node2 AI camera service-layer baseline

- Document validated Node1/Node2 LAN camera pipeline in README
- Add detailed VALIDATION.md with incremental bring-up, issues, fixes, and proof points
- Validate Node2 FastAPI control agent start/stop/switch-profile flow
- Validate Node1 FastAPI API gateway health, camera inventory, and Node2 control path
- Validate Prometheus metrics endpoints for Node1 receiver and Node2 control agent
- Validate SQLite event schema with cameras, clips, and events tables
- Validate motion-triggered event persistence with linked keyframes and MP4 clips
- Add threaded Node1 receiver capture loop to avoid OpenCV cap.read() hangs after stream stop
- Add no-frame/startup watchdog controls for robust headless receiver operation
- Preserve validated MJPEG/YUYV RTP profiles including 480p30, 720p30, 720p60, 1080p30, and YUYV raw debug mode
- Add CI/CD validation plan and initial static/node-local validation scripts

Validated on local LAN:
- Node1 receiver/API gateway: 192.168.29.20
- Node2 Jetson C922 streamer/control agent: 192.168.29.188
```

---

## 30. Roadmap

Planned next extensions:

1. ONNX object detection worker.
2. Object-triggered event/keyframe/clip capture using the same validated evidence chain.
3. Deterministic natural-language query endpoint validation.
4. Qdrant/vector search scaffold validation.
5. Policy enforcement around allowed camera source IPs and runtime profile switching.
6. mTLS between control services.
7. Docker/Compose or systemd service deployment for long-running LAN operation.
8. Web-first owner interface for camera health, events, clips, and natural-language search.
9. Android app after the web/API layer stabilizes.

---

## 31. Summary

This repository is a working foundation for a local-first LAN AI CCTV / USB camera system:

```text
Node2 Jetson Orin Nano + Logitech C922
  -> V4L2 + GStreamer sender profiles
  -> UDP/RTP LAN transport
  -> Node1 OpenCV/GStreamer threaded receiver
  -> display, FPS, JSONL events, Prometheus metrics
  -> SQLite cameras/clips/events metadata
  -> motion-triggered keyframes and clips
  -> Node1/Node2 FastAPI control plane
  -> future ONNX object detection, query, Qdrant, mTLS, and deployment
```

Recommended default run:

```bash
# Node2
./scripts/node2/run_node2_control_agent.sh

# Node1 receiver
python agents/node1/node1_receiver_agent.py   --profile mjpeg_720p30   --port 5000   --camera-id c922_node2_gate   --db-path data/events/ai_camera.db   --metrics   --metrics-port 9101   --motion-events   --no-frame-timeout-sec 10   --startup-timeout-sec 30   --event-log results/node1/events.jsonl

# Start stream from Node1 or any LAN shell
curl -X POST http://192.168.29.188:8082/stream/start   -H 'Content-Type: application/json'   -d '{"node1_ip":"192.168.29.20","port":5000,"profile":"mjpeg_720p30","device":"/dev/video0"}'
```
