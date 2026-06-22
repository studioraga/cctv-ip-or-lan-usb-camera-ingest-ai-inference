# Step 13 — Grafana-triggered capture sessions and dataset artifact pipeline

Step 13 turns the Step 12 timestamped transport into a working local demo:
Grafana/Node1 UI requests a bounded capture, Node1 orchestrates Node2, Node1
writes a source-JPEG dataset, Prometheus records capture metrics, and Grafana
shows the run.

The validated demo uses:

```text
Node1 API / capture UI:  http://192.168.29.20:8080
Prometheus:             http://192.168.29.20:9090
Grafana:                http://192.168.29.20:3000
Node2 control:          http://192.168.29.188:8082
Production RTP UDP:     5000
Capture-session UDP:    5001
```

## 1. Demo behavior

```text
Grafana dashboard / Node1 capture UI
  -> POST Node1 /capture/sessions
  -> Node1 validates duration_sec <= 7200 and policy allow-list
  -> Node1 creates capture_sessions DB row
  -> Node1 binds dataset receiver on AI_CAMERA_CAPTURE_UDP_PORT, default 5001
  -> Node1 asks Node2 /stream/start with transport=timed_jpeg_udp
  -> Node2 sends timestamped source JPEG frames with frame_id and sender timestamps
  -> Node1 writes frames/*.jpg and metadata/frames.jsonl
  -> Node1 stops Node2 when duration expires or the session is cancelled
  -> Node1 finalizes manifest.json, metrics_summary.json, report.md, optional preview.mp4
  -> Prometheus scrapes Node1 API capture metrics
  -> Grafana panels show active status, frame/byte counts, and latency
```

The production receiver remains `AI_CAMERA_TRANSPORT=rtp` on UDP `5000`.
Step 13 capture sessions use the separate UDP `5001` path so the production
receiver does not need to be stopped for a dataset capture.

## 2. API

```http
POST /capture/sessions
GET  /capture/sessions
GET  /capture/sessions/{session_id}
POST /capture/sessions/{session_id}/stop
GET  /capture/sessions/{session_id}/artifacts
GET  /datasets/{session_id}/manifest
GET  /datasets/{session_id}/report
GET  /ui/capture
```

Example request:

```json
{
  "camera_id": "c922_node2_gate",
  "profile": "mjpeg_720p30",
  "duration_sec": 60,
  "device": "/dev/video0",
  "transport": "timed_jpeg_udp",
  "dataset_mode": "source_jpeg",
  "frame_stride": 1,
  "requested_by": "grafana-demo",
  "notes": "demo capture"
}
```

Validation rules:

```text
duration_sec: 1..7200
transport: timed_jpeg_udp for dataset capture
profile/device/target port: must pass SecurityPolicy
only one active capture per camera in the current implementation
```

## 3. Dataset layout

```text
data/datasets/{session_id}/
  manifest.json
  frames/
    frame_000001.jpg
    frame_000002.jpg
    ...
  metadata/
    frames.jsonl
    capture_events.jsonl
  artifacts/
    metrics_summary.json
    report.md
    preview.mp4     # generated when ffmpeg/libx264 are available
```

The frame files are the **source JPEG bytes received from Node2**, not decoded
BGR dumps. This preserves the original payload while avoiding very large raw
frame expansion.

Typical per-frame `metadata/frames.jsonl` record:

```json
{
  "session_id": "cap_20260617_094247_c42c7f87",
  "frame_index": 1,
  "frame_id": 1,
  "sender_wall_ns": 1781669568190709368,
  "sender_monotonic_ns": 3676641776464,
  "receiver_wall_ns": 1781669568208907904,
  "e2e_latency_ms": 18.198536,
  "fragment_count": 161,
  "jpeg_path": "frames/frame_000001.jpg",
  "jpeg_bytes": 193000,
  "sha256": "...",
  "write_latency_ms": 0.407768
}
```

## 4. Prometheus metrics

Node1 API exposes capture-session metrics on `:8080/metrics`:

```text
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

Notes:

- `*_frames_total` and `*_bytes_written_total` are gauges for the active/latest session.
- Histogram counts are cumulative for the Node1 API process lifetime.
- A `session_id` label is intentionally avoided for now to keep Prometheus cardinality low.

Manual metric check:

```bash
curl -fsS http://192.168.29.20:8080/metrics | grep -E \
'ai_camera_capture_session_active|ai_camera_capture_session_frames_total|ai_camera_capture_session_bytes_written_total|ai_camera_capture_session_e2e_latency_ms|ai_camera_capture_session_write_latency_ms'
```

Prometheus query check:

```bash
curl -fsS 'http://192.168.29.20:9090/api/v1/query?query=ai_camera_capture_session_frames_total' \
  | python3 -m json.tool
```

## 5. Grafana and Prometheus stack

Step 13 provisions:

```text
docker/grafana/provisioning/datasources/prometheus.yml
docker/grafana/provisioning/dashboards/ai-camera.yml
docker/grafana/dashboards/ai-camera-capture-session.json
```

Recommended bring-up from Node1:

```bash
./scripts/startup/node1_startup_step13.sh
```

To include a live bounded capture-session test:

```bash
./scripts/startup/node1_startup_step13.sh --capture-test
```

Manual bring-up is also supported:

```bash
./scripts/common/render_prometheus_config.sh
./scripts/validate_step13_grafana_stack.sh
docker compose -f docker/docker-compose.node1.yml up -d
```

Because the compose file is inside `docker/`, these relative mounts are required:

```yaml
../configs/runtime/prometheus.yml:/etc/prometheus/prometheus.yml:ro
./grafana/provisioning:/etc/grafana/provisioning:ro
./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

If Prometheus fails with `not a directory: Are you trying to mount a directory onto a file`,
`configs/runtime/prometheus.yml` was missing or had been created as a directory
by an earlier Compose run. Run `./scripts/common/render_prometheus_config.sh`
again; it removes that stale generated-directory path and writes the expected file.

If Prometheus tries to mount `docker/configs/runtime/prometheus.yml`, the
Prometheus volume path is wrong. If Grafana is healthy but the dashboard is
missing, the Grafana provisioning/dashboard paths are wrong.

Health and provisioning checks:

```bash
curl -fsS http://192.168.29.20:9090/-/healthy
curl -fsS http://192.168.29.20:3000/api/health | python3 -m json.tool
curl -fsS -u admin:admin 'http://192.168.29.20:3000/api/search?query=AI%20Camera' | python3 -m json.tool
```

Expected dashboard:

```text
Folder: AI Camera
Dashboard: AI Camera Capture Session Demo
URL: /d/ai-camera-capture-session-demo/ai-camera-capture-session-demo
```

Open:

```text
http://192.168.29.20:3000/d/ai-camera-capture-session-demo/ai-camera-capture-session-demo
```

Capture form:

```text
http://192.168.29.20:8080/ui/capture
```

## 6. Validation

Source/config validation:

```bash
./scripts/validate_step13_grafana_stack.sh
```

Live capture validation from Node1:

```bash
./scripts/validate_step13_capture_session.sh
```

The live validation starts a short bounded capture, verifies JPEG files,
manifest/report artifacts, Prometheus metrics, and confirms Node2 stream stop.

## 7. Validated live evidence

UI-driven 30-second demo capture:

```text
session_id: cap_20260617_094247_c42c7f87
status: completed
frames_written: 437
bytes_written: 87274343
dropped_frames: 0
avg_fps_written: 12.824
avg e2e latency: 18.186 ms
p95 e2e latency: 18.640 ms
write latency avg: 0.499 ms
preview: artifacts/preview.mp4
```

Automated validation after the UI test:

```text
session_id: cap_20260617_095226_d463178f
status: completed
frames_written: 137
files: 137
[OK] Step 13 capture-session dataset validation completed
```

## 8. Current limitations and next improvements

- `preview.mp4` is best-effort and depends on host `ffmpeg`/`libx264` availability.
- Per-session Prometheus labels are intentionally not used to avoid high-cardinality metrics.
- `metadata/frames.jsonl` is the authoritative per-frame index for later offline analysis.
- Source JPEG datasets can grow quickly for long captures; use `frame_stride` and optional `max_bytes` for controlled runs.
- True camera sensor exposure timestamping is still not implemented; timestamps are assigned by the Node2 userspace timed sender.
