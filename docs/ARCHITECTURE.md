# Architecture: local Node1/Node2 CCTV AI camera platform

This repository implements a local-first CCTV/IP-or-LAN USB camera ingest, evidence, and dataset-capture platform. The validated deployment uses a Logitech C922 USB camera on Node2 Jetson Orin Nano and streams to Node1, where frames are decoded, measured, indexed, stored, and exposed through FastAPI, Prometheus, and Grafana.

The architecture now has two validated frame paths:

1. **Production RTP path**: Node2 GStreamer RTP/JPEG to Node1 UDP `5000`, decoded by OpenCV/GStreamer for live receiver metrics and motion evidence.
2. **Step 13 dataset path**: Node2 timestamped JPEG/UDP to Node1 UDP `5001`, stored as source-JPEG datasets with per-frame metadata and capture-session artifacts.

## Validated nodes

| Node | Validated host/IP | Responsibility | Services |
|---|---|---|---|
| Node1 | `sr-kaaldev` / `192.168.29.20` | API gateway, RTP receiver, timestamped capture-session orchestrator, SQLite event/capture DB, JSONL event log, datasets, keyframes, clips, Prometheus/Grafana/Qdrant stack | `node1-ai-camera-api.service`, `node1-ai-camera-receiver.service`, Docker Prometheus/Grafana/Qdrant |
| Node2 | `shiva-vaisesika` / `192.168.29.188` | Jetson camera control plane, V4L2 camera ownership, GStreamer RTP sender, timestamped JPEG sender, stream lifecycle API | `node2-camera-control-agent.service` |

## Data plane A — production RTP receiver

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

## Data plane B — timestamped dataset capture

```text
Grafana dashboard or Node1 /ui/capture
  -> Node1 POST /capture/sessions
  -> Node1 validates camera/profile/device/port against policy
  -> Node1 starts dataset receiver on UDP 5001
  -> Node1 calls Node2 /stream/start with transport=timed_jpeg_udp
  -> Node2 userspace timed sender reads source JPEG frames from /dev/video0
  -> Node2 fragments each JPEG and attaches frame_id, sender_wall_ns, sender_monotonic_ns
  -> Node1 reassembles source JPEG frames
  -> Node1 writes data/datasets/{session_id}/frames/*.jpg
  -> Node1 writes metadata/frames.jsonl and capture_events.jsonl
  -> Node1 writes manifest.json, metrics_summary.json, report.md, optional preview.mp4
  -> Node1 calls Node2 /stream/stop after duration or cancellation
```

The capture path uses source JPEG bytes, not expanded BGR dumps. This keeps long-running datasets smaller while preserving the original camera payload for offline analysis.

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

Node1 API endpoints now include production control, event/media access, query, capture sessions, and capture UI:

```text
GET  /health
GET  /cameras
GET  /node2/status
POST /cameras/{camera_id}/start
POST /cameras/{camera_id}/stop
POST /cameras/{camera_id}/profile
GET  /events
GET  /clips
POST /query
POST /capture/sessions
GET  /capture/sessions
GET  /capture/sessions/{session_id}
POST /capture/sessions/{session_id}/stop
GET  /capture/sessions/{session_id}/artifacts
GET  /datasets/{session_id}/manifest
GET  /datasets/{session_id}/report
GET  /ui/capture
GET  /metrics
```

## Observability plane

Node1 receiver exposes production receiver metrics on `:9101/metrics`, including frame counts, FPS, decode failures, Step 11 bounded-slices latency metrics, and Step 12 E2E metrics when timed transport is active.

Node1 API exposes API/capture metrics on `:8080/metrics`, including:

```text
ai_camera_api_requests_total
ai_camera_api_errors_total
ai_camera_capture_session_active
ai_camera_capture_sessions_total
ai_camera_capture_session_elapsed_seconds
ai_camera_capture_session_frames_total
ai_camera_capture_session_bytes_written_total
ai_camera_capture_session_dropped_frames_total
ai_camera_capture_session_e2e_latency_ms
ai_camera_capture_session_write_latency_ms
ai_camera_capture_session_disk_free_bytes
ai_camera_capture_session_errors_total
```

Prometheus and Grafana run from `docker/docker-compose.node1.yml` using host networking. Prometheus config is rendered to `configs/runtime/prometheus.yml`, and Grafana provisions the **AI Camera Capture Session Demo** dashboard from `docker/grafana/dashboards/ai-camera-capture-session.json`.

## Persistence and evidence plane

The event DB is migration-managed by `migrations/` and accessed through `services/common/event_db.py`.

Current persistence layers:

```text
data/events/ai_camera.db                       # SQLite events, clips, capture sessions, artifacts
results/node1/events.jsonl                     # receiver JSONL events
data/keyframes/                                # motion keyframes
data/clips/                                    # motion clips
data/datasets/{session_id}/                    # Step 13 source-JPEG datasets
```

Step 13 adds `capture_sessions` and `capture_artifacts` through `migrations/003_capture_sessions.sql`.

## Security plane

The security model is fail-closed and policy-driven:

- Node2 stream-control endpoints require a trusted Node1 control IP.
- Node2 validates stream profile, target Node1 IP/port, camera ID, device path, and transport.
- Node1 capture sessions validate duration, device, profile, transport, and capture UDP target.
- Node1 media and dataset artifact access is identifier-based; callers should request artifacts by database/session IDs, not arbitrary filesystem paths.
- Systemd units use `NoNewPrivileges=true`, restrictive `ReadWritePaths`, and explicit device access on Node2.

## Runtime dependency rule

Node1 must use apt/system OpenCV with GStreamer enabled. The Node1 `.venv` must be created with `python3 -m venv --system-site-packages .venv`. Installing `opencv-python` in Node1 `.venv` breaks the receiver because PyPI OpenCV commonly reports `GStreamer: NO`.

The validated fixed state is:

```text
Node1 .venv Python: repo .venv
OpenCV: 4.6.0
GStreamer: YES (1.24.1)
```
