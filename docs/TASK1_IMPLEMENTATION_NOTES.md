# Task1 Implementation Notes

This repository extends the working Node1/Node2 camera transport into a local-first AI CCTV service, event, latency, inference, and dataset-capture platform.

## Implemented components

1. Node1 RTP/JPEG receiver with `mjpeg_480p30`, `mjpeg_720p30`, `mjpeg_720p60`, `mjpeg_1080p30`, and raw debug profile support.
2. Node2 GStreamer/V4L2 streamer controller under `agents/node2/node2_streamer_controller.py`.
3. Node2 timestamped JPEG/UDP sender under `agents/node2/node2_timed_jpeg_sender.py`.
4. Node2 FastAPI control agent under `services/node2_control_agent/`.
5. Node1 FastAPI API gateway under `services/node1_api_gateway/`.
6. Node1 capture-session orchestrator and dataset writer under `services/node1_capture_orchestrator/`.
7. Prometheus metrics for Node1 receiver, Node1 API/capture sessions, and Node2 control service.
8. Grafana/Prometheus/Qdrant Node1 Docker stack with provisioned AI Camera dashboard.
9. Migration-managed SQLite schema through `migrations/` and `services/common/event_db.py`.
10. Motion-event generation with event rows, JSONL records, keyframe JPGs, and MP4 clips.
11. Step 11 bounded-slices latency monitoring for Node1 receiver-side frame timing stability.
12. Step 12 sender-to-Node1 E2E timestamped latency path using `timed_jpeg_udp`.
13. Step 12 YOLO ONNX post-processing for common YOLOv5/YOLOv8 exports.
14. Step 13 bounded capture sessions with source-JPEG datasets, per-frame metadata, manifest, report, metrics summary, and optional preview MP4.
15. Secure media/dataset artifact retrieval using opaque IDs/session IDs and path-containment checks.
16. Policy validation, systemd templates, portable deployment scripts, and validation gates.

## Validated end-to-end flows

### Production RTP flow

```text
Node1 trusted control client
  -> POST Node2 /stream/start transport=rtp
  -> Node2 gst-launch-1.0 owns /dev/video0
  -> RTP/JPEG to Node1 UDP/5000
  -> Node1 receiver decodes frames through OpenCV/GStreamer
  -> metrics show ~15 FPS and increasing frames_total
  -> motion_detected events are written to JSONL and SQLite
  -> Node1 POST Node2 /stream/stop
  -> Node2 sends EOS, frees pipeline, /dev/video0 becomes available
```

### Timestamped E2E validation flow

```text
Node1 starts manual timed receiver
  -> Node2 /stream/start transport=timed_jpeg_udp
  -> Node2 sends frame_id + sender_wall_ns + JPEG fragments
  -> Node1 reassembles and decodes frames
  -> Node1 exports ai_camera_e2e_latency_ms and e2e bounded-slices metrics
```

### Grafana capture-session flow

```text
Grafana dashboard / Node1 /ui/capture
  -> POST Node1 /capture/sessions
  -> Node1 validates duration <= 7200 sec
  -> Node1 starts dataset receiver on UDP/5001
  -> Node1 starts Node2 transport=timed_jpeg_udp
  -> Node1 writes data/datasets/{session_id}/frames/*.jpg
  -> Node1 writes metadata/frames.jsonl, manifest.json, metrics_summary.json, report.md, preview.mp4
  -> Prometheus scrapes Node1 capture metrics
  -> Grafana panels show capture state and metrics
  -> Node1 stops Node2 at the end of the bounded capture
```

## Validated Step 13 evidence

```text
UI capture session: cap_20260617_094247_c42c7f87
status: completed
frames_written: 437
bytes_written: 87274343
dropped_frames: 0
avg e2e latency: ~18.19 ms
p95 e2e latency: ~18.64 ms
write latency avg: ~0.50 ms
preview.mp4 generated

Automated validation session: cap_20260617_095226_d463178f
status: completed
frames_written: 137
[OK] Step 13 capture-session dataset validation completed
```

## Important operational findings

| Finding | Impact | Permanent handling |
|---|---|---|
| Node1 PyPI OpenCV reported `GStreamer: NO` | Receiver could not open RTP pipeline | Node1 venv setup now validates `GStreamer: YES` and uses `--system-site-packages` |
| Manual sender and API sender cannot both own `/dev/video0` | API start can exit with rc=1 and `Device busy` | Stop manual `gst-launch` or timed sender before API streaming |
| Node2 local `/stream/status` can return 403 | Policy trusts Node1, not every local caller | Query Node2 stream-control endpoints from Node1 |
| Runtime artifacts appeared in archives | Source archives become large/non-portable | `.gitignore` and sync exclusions exclude `.venv`, DBs, clips, keyframes, datasets, pycache, results |
| RTP/JPEG does not carry sender timestamps | True sender-to-receiver latency cannot be measured on RTP path | Step 12 adds opt-in `timed_jpeg_udp` with frame IDs and sender timestamps |
| Grafana dashboard did not appear initially | Compose paths are relative to `docker/docker-compose.node1.yml` | Use `./grafana/...` from inside `docker/`, not `./docker/grafana/...` |
| Prometheus mount initially pointed to `docker/configs/runtime/prometheus.yml` | Prometheus container failed to start | Use `../configs/runtime/prometheus.yml` |
| Capture histograms accumulate across runs | Counts can exceed latest session frame gauge | This is normal Prometheus histogram behavior; latest-session gauges remain separate |

## Current functional status

```text
Step 9 API-controlled production RTP streaming: PASS
Step 10.2 reproducible deployment validation: PASS
Step 11 bounded-slices receiver latency monitoring: PASS
Step 12 timestamped E2E latency validation: PASS
Step 12 YOLO ONNX postprocess validation: PASS
Step 13 Grafana/Prometheus stack validation: PASS
Step 13 UI/API capture-session dataset validation: PASS
```

## Next implementation direction

The next clean task after committing Step 13 is to harden and scale the capture demo:

1. Add an optional per-session latest-summary endpoint for Grafana JSON/API panels.
2. Add disk-space preflight and user-visible estimated dataset size before starting long captures.
3. Add dataset cleanup/archive commands for large `data/datasets/` runs.
4. Add optional `frame_stride` presets for long captures up to 2 hours.
5. Add a true sensor-exposure timestamp path using V4L2 buffer timestamps if precise camera exposure timing becomes required.
6. Move FastAPI startup from deprecated `on_event` to lifespan handlers.
