# AI Camera Node1/Node2 Agent Framework

A two-node LAN camera streaming and AI-agent orchestration lab using a **Logitech C922 Pro Stream Webcam** on **Node2 Jetson Orin Nano** and a **Node1 x86 workstation** receiver running **GStreamer + OpenCV + optional ONNX Runtime**.

This repository is designed as a practical starting point for local AI camera systems: camera streaming, frame reception, FPS measurement, display, event logging, ONNX inference hooks, policy artifacts, telemetry, and future AI-agent orchestration.

---

## 1. What this project does

The current working system streams camera frames from Node2 to Node1 over the LAN:

```text
Logitech C922 USB Camera
  -> Node2 Jetson Orin Nano
  -> V4L2 /dev/video0
  -> GStreamer sender
  -> RTP over UDP port 5000
  -> Node1 receiver
  -> GStreamer depayload/decode
  -> OpenCV BGR frames
  -> optional display / FPS / ONNX Runtime inference / JSONL event logs
```

Default tested node mapping:

| Node  |          Role              | IP               | Main function                                                                       |
|-------|----------------------------|-----------------:|-------------------------------------------------------------------------------------|
| Node1 | Receiver / AI orchestrator | `192.168.29.20`  | Receives RTP stream, decodes frames, displays, logs events, optional ONNX inference |
| Node2 | Camera streamer            | `192.168.29.188` | Captures C922 frames through V4L2 and streams to Node1                              |

Default transport:

```text
UDP/RTP port 5000
```

Supported active stream profiles:

| Profile         | Sender format                              | Resolution | FPS | RTP payload | Status                                |
|-----------------|--------------------------------------------|-----------:|----:|------------:|---------------------------------------|
| `mjpeg_480p30`  | MJPEG / RTP JPEG                           | 640x480    | 30  | 26          | Working sender profile                |
| `mjpeg_720p30`  | MJPEG / RTP JPEG                           | 1280x720   | 30  | 26          | Recommended baseline                  |
| `mjpeg_720p60`  | MJPEG / RTP JPEG                           | 1280x720   | 60  | 26          | High-FPS test                         |
| `mjpeg_1080p30` | MJPEG / RTP JPEG                           | 1920x1080  | 30  | 26          | High-resolution test                  |
| `yuyv_640x480`  | Raw YUYV converted to UYVY / RTP raw video | 640x480    | 30  | 96          | Raw low-resolution debug/test profile |

---

## 2. Current achievements captured in this repository

This repository consolidates the work completed during the Node1/Node2 bring-up:

1. The Logitech C922 camera was detected on Node2 as a USB UVC/V4L2 camera.
2. `/dev/video0` was confirmed as the active camera capture node.
3. C922 modes were validated through `v4l2-ctl` and FFmpeg format listing.
4. MJPEG streaming over RTP/UDP was selected as the stable LAN transport path.
5. The original H.264 hardware encoder path was intentionally avoided because `nvv4l2h264enc` was not present on the tested Jetson Orin Nano environment.
6. Node2 can stream `mjpeg_480p30`, `mjpeg_720p30`, `mjpeg_720p60`, `mjpeg_1080p30`, and `yuyv_640x480` profiles.
7. Node1 can receive MJPEG and YUYV/raw RTP profiles through OpenCV/GStreamer.
8. Node1 receiver runs inside a project-local Python `.venv` while preserving system OpenCV with GStreamer support.
9. Node2 controller runs inside a separate architecture-local Python `.venv`.
10. Node1 event logging writes JSONL telemetry under `results/node1/`.
11. Node2 optional `tegrastats` logging writes thermal/power/system statistics under `results/node2/`.
12. A C++ OpenCV/GStreamer probe is included for native receiver validation.
13. Policy, config, architecture notes, and repo sync scripts are included for GitHub-ready project organization.

---

## 3. Important design decision: do not sync `.venv`

Use one source repository on both nodes, but create a separate `.venv` on each node.

Do **not** copy or sync `.venv` between Node1 and Node2.

Reason:

```text
Node1: x86_64 Ubuntu workstation
Node2: aarch64 Jetson Orin Nano
```

Python native wheels, OpenCV bindings, ONNX Runtime packages, and linked libraries are architecture-specific.

Correct pattern:

```text
Sync source code, scripts, configs, requirements.
Recreate .venv separately on each node.
Exclude .venv, __pycache__, results, and large media files from rsync/Git.
```

---

## 4. Repository layout

```text
.
├── README.md
├── LICENSE
├── .gitignore
├── requirements-node1.txt
├── requirements-node2.txt
├── configs/
│   └── nodes.yaml
├── policies/
│   └── security_policy.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   └── VENV_SETUP.md
├── agents/
│   ├── common/
│   │   └── telemetry.py
│   ├── node1/
│   │   ├── node1_receiver_agent.py
│   │   └── node1_receiver_agent.py.bak
│   └── node2/
│       ├── node2_streamer_controller.py
│       └── node2_streamer_controller.py.back
├── scripts/
│   ├── common/
│   │   └── sync_repo_to_node2.sh
│   ├── node1/
│   │   ├── install_node1_dependencies.sh
│   │   ├── setup_node1_venv.sh
│   │   ├── run_node1_receiver_agent.sh
│   │   ├── 01_opencv_install_node1.sh
│   │   ├── node1_reciever_mjpeg_720p30.sh
│   │   ├── node1_receiver_fps_only.py
│   │   ├── node1_receiver_display.py
│   │   └── node1_receiver_OpenCV_ai_orchestration.py
│   └── node2/
│       ├── install_node2_dependencies.sh
│       ├── setup_node2_venv.sh
│       ├── run_node2_streamer_controller.sh
│       ├── node2_sender_mjpeg_480p30.sh
│       ├── node2_sender_mjpeg_720p30.sh
│       ├── node2_sender_mjpeg_720p60.sh
│       └── node2_sender_720p30.sh
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

### Main files

| File | Purpose |
|---|---|
| `agents/node1/node1_receiver_agent.py` | Main Node1 Python receiver agent with MJPEG/YUYV profiles, display, FPS, event log, optional ONNX inference |
| `agents/node2/node2_streamer_controller.py` | Main Node2 Python streamer controller that launches GStreamer sender pipelines |
| `scripts/node1/setup_node1_venv.sh` | Creates Node1 `.venv` with `--system-site-packages` and installs Node1 Python requirements |
| `scripts/node2/setup_node2_venv.sh` | Creates Node2 `.venv` and installs Node2 Python requirements |
| `scripts/node1/run_node1_receiver_agent.sh` | Wrapper for running Node1 receiver agent from `.venv` |
| `scripts/node2/run_node2_streamer_controller.sh` | Wrapper for running Node2 streamer controller from `.venv` |
| `scripts/common/sync_repo_to_node2.sh` | Rsync helper that excludes `.venv`, caches, and results |
| `cpp/node1_frame_probe/` | C++ OpenCV/GStreamer receiver probe |
| `tools/parse_tegrastats.py` | Parses Node2 `tegrastats` logs |
| `configs/nodes.yaml` | Node/IP/config reference |
| `policies/security_policy.yaml` | Local LAN policy reference for UDP/5000 camera traffic |

---

## 5. Prerequisites

### Node1 receiver machine

Tested role: x86 workstation receiver.

Required system packages:

```bash
sudo apt update
sudo apt install -y \
  python3-full python3-venv python3-pip python3-opencv python3-numpy \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  build-essential cmake pkg-config libopencv-dev \
  ufw iproute2 net-tools htop
```

The key requirement is **OpenCV with GStreamer support**. The project expects system `python3-opencv` to provide `cv2` with `GStreamer: YES`.

Avoid installing pip `opencv-python` for this project unless you know your wheel has GStreamer enabled. Many pip OpenCV wheels do not include GStreamer support.

### Node2 streamer machine

Tested role: Jetson Orin Nano camera streamer.

Required system packages:

```bash
sudo apt update
sudo apt install -y \
  v4l-utils ffmpeg \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  python3-full python3-venv python3-pip htop iproute2 net-tools
```

Node2 streams through GStreamer; Python only controls the selected profile and optional `tegrastats` logging.

---

## 6. Node1 setup

From the repo root on Node1:

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework
```

Install dependencies:

```bash
chmod +x scripts/node1/install_node1_dependencies.sh
./scripts/node1/install_node1_dependencies.sh
```

Recommended venv setup:

```bash
chmod +x scripts/node1/setup_node1_venv.sh
./scripts/node1/setup_node1_venv.sh
source .venv/bin/activate
```

The venv script uses:

```bash
python3 -m venv --system-site-packages .venv
```

This is intentional so that the venv can see apt-installed `python3-opencv` with GStreamer support.

Validate Node1 Python environment:

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

Expected key result:

```text
GStreamer: YES
```

---

## 7. Node2 setup

From the repo root on Node2:

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework
```

Install dependencies and create `.venv`:

```bash
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

---

## 8. Quick start: baseline MJPEG 720p30

### Terminal 1: Node1 receiver

Run this first on Node1:

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework
source .venv/bin/activate

python agents/node1/node1_receiver_agent.py \
  --profile mjpeg_720p30 \
  --port 5000 \
  --buffer-size 8388608 \
  --display \
  --event-log results/node1/mjpeg_720p30_events.jsonl
```

Or use the wrapper:

```bash
./scripts/node1/run_node1_receiver_agent.sh --display
```

### Terminal 2: Node2 sender

Run this on Node2:

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework
source .venv/bin/activate

python agents/node2/node2_streamer_controller.py \
  --node1-ip 192.168.29.20 \
  --profile mjpeg_720p30 \
  --tegrastats
```

Or use the wrapper:

```bash
NODE1_IP=192.168.29.20 PROFILE=mjpeg_720p30 \
  ./scripts/node2/run_node2_streamer_controller.sh --tegrastats
```

Expected Node2 pipeline:

```text
v4l2src device=/dev/video0 io-mode=2 do-timestamp=true
  ! image/jpeg,width=1280,height=720,framerate=30/1
  ! queue leaky=downstream max-size-buffers=2
  ! rtpjpegpay pt=26
  ! udpsink host=192.168.29.20 port=5000 sync=false async=false
```

Expected Node1 output:

```text
[INFO] profile=mjpeg_720p30, FPS=..., frame=(720, 1280, 3), infer_ms=None
```

If `--display` is provided and Node1 has a GUI session, an OpenCV window should appear.

---

## 9. Running all profiles

### 9.1 MJPEG 480p30

Node1:

```bash
python agents/node1/node1_receiver_agent.py \
  --profile mjpeg_720p30 \
  --port 5000 \
  --buffer-size 8388608 \
  --display \
  --event-log results/node1/mjpeg_480p30_events.jsonl
```

Note: the Node1 MJPEG receiver pipeline accepts RTP/JPEG payload 26. The current receiver agent profiles explicitly define 720p/1080p MJPEG modes, but the RTP/JPEG caps do not require width/height at the receiver side. `mjpeg_720p30` can still receive the `mjpeg_480p30` sender because the decoded frame size comes from the stream.

Node2:

```bash
python agents/node2/node2_streamer_controller.py \
  --node1-ip 192.168.29.20 \
  --profile mjpeg_480p30 \
  --tegrastats
```

### 9.2 MJPEG 720p30

Node1:

```bash
python agents/node1/node1_receiver_agent.py \
  --profile mjpeg_720p30 \
  --port 5000 \
  --buffer-size 8388608 \
  --display \
  --event-log results/node1/mjpeg_720p30_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py \
  --node1-ip 192.168.29.20 \
  --profile mjpeg_720p30 \
  --tegrastats
```

### 9.3 MJPEG 720p60

Node1:

```bash
python agents/node1/node1_receiver_agent.py \
  --profile mjpeg_720p60 \
  --port 5000 \
  --buffer-size 8388608 \
  --display \
  --event-log results/node1/mjpeg_720p60_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py \
  --node1-ip 192.168.29.20 \
  --profile mjpeg_720p60 \
  --tegrastats
```

### 9.4 MJPEG 1080p30

Node1:

```bash
python agents/node1/node1_receiver_agent.py \
  --profile mjpeg_1080p30 \
  --port 5000 \
  --buffer-size 16777216 \
  --jitterbuffer \
  --jitter-latency-ms 80 \
  --display \
  --event-log results/node1/mjpeg_1080p30_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py \
  --node1-ip 192.168.29.20 \
  --profile mjpeg_1080p30 \
  --tegrastats
```

### 9.5 YUYV 640x480 raw RTP

This mode is useful as a low-resolution raw-video debug path.

Node2 captures C922 as `YUY2`, converts it to `UYVY`, and sends raw RTP video:

```text
v4l2src -> video/x-raw,format=YUY2 -> videoconvert -> video/x-raw,format=UYVY -> rtpvrawpay pt=96 -> UDP
```

Node1:

```bash
python agents/node1/node1_receiver_agent.py \
  --profile yuyv_640x480 \
  --port 5000 \
  --buffer-size 8388608 \
  --display \
  --event-log results/node1/yuyv_640x480_events.jsonl
```

Node2:

```bash
python agents/node2/node2_streamer_controller.py \
  --node1-ip 192.168.29.20 \
  --profile yuyv_640x480 \
  --tegrastats
```

The `videoconvert -> UYVY` step is important. Directly linking `YUY2 -> rtpvrawpay` caused the earlier GStreamer error:

```text
could not link queue0 to rtpvrawpay0
```

---

## 10. Direct GStreamer validation commands

These commands are useful when debugging without Python.

### 10.1 Node2 local camera FPS test

Run on Node2:

```bash
gst-launch-1.0 -v \
  v4l2src device=/dev/video0 io-mode=2 do-timestamp=true ! \
  image/jpeg,width=1280,height=720,framerate=30/1 ! \
  queue leaky=downstream max-size-buffers=2 ! \
  fpsdisplaysink video-sink=fakesink text-overlay=false sync=false
```

### 10.2 Node1 pure GStreamer MJPEG receiver

Run on Node1 before starting Node2 sender:

```bash
gst-launch-1.0 -v \
  udpsrc port=5000 buffer-size=8388608 \
  caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26" ! \
  queue leaky=downstream max-size-buffers=4 ! \
  rtpjpegdepay ! \
  jpegdec ! \
  videoconvert ! \
  fpsdisplaysink video-sink=fakesink text-overlay=false sync=false
```

### 10.3 Node1 pure GStreamer YUYV/raw receiver

```bash
gst-launch-1.0 -v \
  udpsrc port=5000 buffer-size=8388608 \
  caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=RAW,payload=96,sampling=YCbCr-4:2:2,depth=(string)8,width=(string)640,height=(string)480,colorimetry=(string)BT601-5,a-framerate=(string)30.000000" ! \
  queue leaky=downstream max-size-buffers=4 ! \
  rtpvrawdepay ! \
  videoconvert ! \
  fpsdisplaysink video-sink=fakesink text-overlay=false sync=false
```

### 10.4 Node2 direct YUYV sender

```bash
gst-launch-1.0 -v -e \
  v4l2src device=/dev/video0 io-mode=2 do-timestamp=true ! \
  video/x-raw,format=YUY2,width=640,height=480,framerate=30/1 ! \
  videoconvert ! \
  video/x-raw,format=UYVY ! \
  queue leaky=downstream max-size-buffers=2 ! \
  rtpvrawpay pt=96 ! \
  udpsink host=192.168.29.20 port=5000 sync=false async=false
```

---

## 11. ONNX Runtime inference hook on Node1

The main receiver agent supports an optional model path:

```bash
python agents/node1/node1_receiver_agent.py \
  --profile mjpeg_720p30 \
  --port 5000 \
  --display \
  --model models/example.onnx \
  --event-log results/node1/onnx_events.jsonl
```

The current preprocessing in `OptionalOnnxModel.infer()` is intentionally generic:

```text
BGR frame -> resize 224x224 -> RGB -> float32 / 255 -> CHW -> NCHW -> ONNX Runtime
```

For a real model, update the preprocessing to match the model’s exact input shape, normalization, channel order, and output decoding.

Node1 `requirements-node1.txt` includes:

```text
numpy>=1.23,<2.0
onnxruntime>=1.17
PyYAML>=6.0
prometheus-client>=0.20
```

---

## 12. Event logs and telemetry

Node1 writes JSONL events such as:

```json
{"event": "receiver_started", "profile": "mjpeg_720p30", "port": 5000}
{"event": "receiver_fps", "profile": "mjpeg_720p30", "fps": 28.7, "frame_shape": [720, 1280, 3]}
{"event": "receiver_stopped", "profile": "mjpeg_720p30", "frames_total": 1000}
```

Default event log location:

```text
results/node1/events.jsonl
```

Node2 can collect `tegrastats` with:

```bash
python agents/node2/node2_streamer_controller.py \
  --node1-ip 192.168.29.20 \
  --profile mjpeg_720p30 \
  --tegrastats \
  --tegrastats-log results/node2/camera_stream_tegrastats.log
```

Parse `tegrastats` output:

```bash
python tools/parse_tegrastats.py results/node2/camera_stream_tegrastats.log
```

---

## 13. C++ receiver probe

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

## 14. Syncing source from Node1 to Node2

From the source machine:

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework

NODE2_USER=srrmk \
NODE2_IP=192.168.29.188 \
REMOTE_DIR=~/dev/ai-camera-node1-node2-agent-framework \
./scripts/common/sync_repo_to_node2.sh
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

## 15. Network and firewall checklist

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

The policy artifact is stored at:

```text
policies/security_policy.yaml
```

It documents the intended rule:

```text
Allow Node2 192.168.29.188 -> Node1 192.168.29.20 UDP/5000
Deny untrusted camera sources
Require metrics/event logs/tegrastats
```

---

## 16. Performance and optimization notes

### 16.1 UDP socket buffers

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

### 16.2 Receiver buffer size

Use larger receiver buffers for 1080p:

```bash
--buffer-size 16777216
```

### 16.3 Jitter buffer

For 1080p or unstable LAN conditions:

```bash
--jitterbuffer --jitter-latency-ms 80
```

### 16.4 CPU pinning on Node2

The Node2 sender uses:

```bash
taskset -c 0-3
```

This gives repeatable CPU placement for camera streaming tests.

### 16.5 Jetson monitoring

Run with:

```bash
--tegrastats
```

or manually:

```bash
sudo tegrastats
```

### 16.6 Jetson clock mode

For repeatable benchmarks, use Jetson performance mode carefully:

```bash
sudo nvpmodel -q
sudo jetson_clocks
```

Use this only when you understand the power and thermal impact.

---

## 17. Known issue: `nvv4l2h264enc` path is not the active path

The file below exists as an older experiment:

```text
scripts/node2/node2_sender_720p30.sh
```

It attempts an H.264 hardware encoding pipeline using:

```text
nvv4l2h264enc
```

On the tested Jetson Orin Nano setup, this element was not available:

```text
No such element or plugin 'nvv4l2h264enc'
```

Do not use this script as the default path. Use the MJPEG RTP scripts or the Python controller instead:

```bash
python agents/node2/node2_streamer_controller.py --profile mjpeg_720p30 --node1-ip 192.168.29.20
```

Recommended active path:

```text
C922 MJPEG -> rtpjpegpay -> UDP -> rtpjpegdepay -> jpegdec -> OpenCV
```

---

## 18. Troubleshooting

### 18.1 Node1 receives frames but no OpenCV window appears

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

### 18.2 `ffplay` says no video device or DISPLAY is not set

That is a GUI/session problem, not necessarily a camera problem. Use headless recording or GStreamer fakesink tests.

### 18.3 `cv2.VideoCapture(..., cv2.CAP_GSTREAMER)` fails

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

### 18.4 Low FPS on Node1

Test in layers:

1. Node2 local camera FPS with `fpsdisplaysink`.
2. Node1 pure GStreamer receiver with `fpsdisplaysink video-sink=fakesink`.
3. Node1 Python/OpenCV receiver.
4. Node1 Python/OpenCV display receiver.

If pure GStreamer is fast but Python is slow, the bottleneck is the Python/OpenCV loop or display path. If pure GStreamer is also slow, check LAN packet loss, socket buffers, camera mode, USB link, and system load.

### 18.5 YUYV sender fails with `could not link queue0 to rtpvrawpay0`

Use the corrected path:

```text
YUY2 -> videoconvert -> UYVY -> queue -> rtpvrawpay
```

The active Node2 controller already uses this corrected path.

### 18.6 Verify generated Node2 commands

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

### 18.7 Validate Python syntax

```bash
python3 -m py_compile agents/node1/node1_receiver_agent.py
python3 -m py_compile agents/node2/node2_streamer_controller.py
python3 -m py_compile agents/common/telemetry.py
python3 -m py_compile tools/parse_tegrastats.py
```

---

## 19. GitHub preparation checklist

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
results/**/*.jsonl
results/**/*.log
*.mp4
*.mkv
*.mjpg
*.onnx
build/
.DS_Store
.vscode/
.idea/
```

Decide whether to commit sample logs under `results/`. For a clean public repository, it is usually better to commit a small `results/README.md` or `.gitkeep`, but not large generated logs.

---

## 22. Roadmap

Planned next extensions:

1. Add explicit `mjpeg_480p30` receiver profile for symmetry with Node2.
2. Add REST/gRPC control plane between Node1 and Node2.
3. Add Prometheus metrics endpoint for Node1 receiver FPS/inference latency.
4. Add model-specific ONNX preprocessing and output decoding examples.
5. Add object detection event triggers and clip capture.
6. Add mTLS between control services.
7. Add policy enforcement around allowed camera source IPs and runtime profile switching.
8. Add Docker/Compose or systemd service deployment for long-running LAN operation.

---

## 21. Summary

This repository is a working foundation for a local LAN AI camera system:

```text
Node2 Jetson Orin Nano + Logitech C922
  -> V4L2 + GStreamer sender profiles
  -> UDP/RTP LAN transport
  -> Node1 OpenCV/GStreamer receiver
  -> display, FPS, JSONL events, ONNX Runtime inference hook
  -> future AI-agent orchestration, security policy, and observability
```

Recommended default run:

```bash
# Node1
python agents/node1/node1_receiver_agent.py --profile mjpeg_720p30 --port 5000 --display

# Node2
python agents/node2/node2_streamer_controller.py --node1-ip 192.168.29.20 --profile mjpeg_720p30 --tegrastats
```
