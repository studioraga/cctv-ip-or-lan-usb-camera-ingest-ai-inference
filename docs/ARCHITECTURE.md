# Architecture: local Node1/Node2 CCTV AI camera platform

This repository implements a local-first CCTV/IP-or-LAN USB camera ingest and AI evidence pipeline. The validated deployment uses a Logitech C922 USB camera on Node2 Jetson Orin Nano and streams RTP/JPEG over the LAN to Node1, where frames are decoded, measured, indexed, and converted into motion-event evidence.

## Validated nodes

| Node | Validated host/IP | Responsibility | Services |
|---|---|---|---|
| Node1 | `sr-kaaldev` / `192.168.29.20` | API gateway, RTP receiver, GStreamer/OpenCV decode, SQLite event DB, JSONL event log, keyframes, clips, receiver metrics | `node1-ai-camera-api.service`, `node1-ai-camera-receiver.service` |
| Node2 | `shiva-vaisesika` / `192.168.29.188` | Jetson camera control plane, V4L2 camera ownership, GStreamer RTP sender, stream lifecycle API | `node2-camera-control-agent.service` |

## Data plane

```text
Logitech C922 on Node2 /dev/video0
  -> V4L2 MJPEG 1280x720@30
  -> gst-launch-1.0 v4l2src
  -> rtpjpegpay payload=26
  -> UDP/RTP to Node1 192.168.29.20:5000
  -> Node1 udpsrc/rtpjpegdepay/jpegdec/videoconvert
  -> OpenCV BGR frames [720, 1280, 3]
  -> motion scoring / optional inference
  -> JSONL events + SQLite rows + keyframe JPG + clip MP4
```

Validated RTP sender command shape:

```bash
gst-launch-1.0 -v -e \
  v4l2src device=/dev/video0 io-mode=2 do-timestamp=true \
  ! image/jpeg,width=1280,height=720,framerate=30/1 \
  ! queue leaky=downstream max-size-buffers=2 \
  ! rtpjpegpay pt=26 \
  ! udpsink host=192.168.29.20 port=5000 sync=false async=false
```

Validated receiver pipeline shape:

```text
udpsrc port=5000 buffer-size=8388608
  caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26"
  ! queue leaky=downstream max-size-buffers=4
  ! rtpjpegdepay
  ! jpegdec
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true sync=false max-buffers=1 wait-on-eos=false emit-signals=false
```

## Control plane

Node1 is the trusted controller. Node2 exposes a FastAPI control service on `192.168.29.188:8082`. Policy allows Node1 to call control endpoints and denies untrusted clients. This is why `/health` works locally on Node2, but `/stream/status` can return `403` when called from Node2 itself if Node2 is not in the trusted control-client allow-list.

Validated Node2 control endpoints:

```text
GET  /health
GET  /camera/devices
GET  /stream/profiles
GET  /stream/status
POST /stream/start
POST /stream/stop
POST /stream/switch-profile
GET  /metrics
```

Validated API start payload from Node1:

```json
{
  "camera_id": "c922_node2_gate",
  "node1_ip": "192.168.29.20",
  "port": 5000,
  "device": "/dev/video0",
  "profile": "mjpeg_720p30"
}
```

## Observability plane

Node1 receiver exposes Prometheus metrics on `:9101/metrics`. The Step 9 validation showed `ai_camera_receiver_fps` around 14.9-15.1 FPS and `ai_camera_frames_total` increasing continuously during API-controlled streaming.

Node1 also writes local evidence:

```text
results/node1/events.jsonl
data/events/ai_camera.db
data/keyframes/*.jpg
data/clips/c922_node2_gate/YYYY-MM-DD/*.mp4
```

## Persistence and evidence plane

The event DB is migration-managed by `migrations/` and accessed through `services/common/event_db.py`. Motion events are written with `event_id`, `camera_id`, `event_type`, timestamp, confidence, clip ID/path, keyframe path, label, severity, and attributes such as `motion_score`.

## Security plane

The security model is fail-closed and policy-driven:

- Node2 stream-control endpoints require a trusted Node1 control IP.
- Node2 validates stream profile, target Node1 IP/port, camera ID, and device path before launching GStreamer.
- Node1 media access is identifier-based; callers should request media by database IDs, not arbitrary filesystem paths.
- Systemd units use `NoNewPrivileges=true`, restrictive `ReadWritePaths`, and explicit device access on Node2.

## Runtime dependency rule

Node1 must use apt/system OpenCV with GStreamer enabled. The Node1 `.venv` must be created with `python3 -m venv --system-site-packages .venv`. Installing `opencv-python` in Node1 `.venv` breaks the receiver because PyPI OpenCV commonly reports `GStreamer: NO`.

The validated fixed state is:

```text
Node1 .venv Python: repo .venv
OpenCV: 4.6.0
GStreamer: YES (1.24.1)
```
