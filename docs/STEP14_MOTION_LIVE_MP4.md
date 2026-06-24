# Step 14 — Node1 API endpoint for motion-triggered live MP4 stream

Goal: make the next milestone meaningful and product-aligned:

> Node2 detects or reports motion, then Node1 starts a bounded live MP4-capable capture session, exposes a LAN-viewable MP4 stream URL while recording, and stores finalized MP4 artifacts for later review.

This builds on Step 13. The transport remains `timed_jpeg_udp` from Node2 to Node1 so Node1 keeps sender timestamps, dataset evidence, latency metrics, and reproducible artifacts.

## Architecture

```text
Node2 C922 camera
  -> Node2 motion detector / Node2-style motion event
  -> POST Node1 /motion/events/node2
  -> Node1 CaptureSessionManager
       - starts Node2 timed_jpeg_udp sender
       - receives timestamped JPEG frames on Node1 UDP 5001
       - writes source JPEG evidence dataset
       - pipes frames to ffmpeg fragmented MP4 writer
       - generates preview.mp4 after completion
       - stores artifacts in SQLite
  -> LAN viewers
       - /motion/streams/{session_id}/live.mp4
       - /motion/streams/{session_id}/preview.mp4
```

## API endpoints

### Start a motion-triggered stream manually

```bash
curl -fsS -X POST http://192.168.29.20:8080/motion/streams/start \
  -H 'Content-Type: application/json' \
  -d '{
    "camera_id": "c922_node2_gate",
    "profile": "mjpeg_720p30",
    "duration_sec": 60,
    "device": "/dev/video0",
    "motion_score": 1.0,
    "motion_source": "manual_validation",
    "requested_by": "step14_manual",
    "notes": "Manual validation of motion-triggered live MP4 stream"
  }' | python3 -m json.tool
```

### Node2-style motion webhook

A Node2-side detector should call this when motion is detected:

```bash
curl -fsS -X POST http://192.168.29.20:8080/motion/events/node2 \
  -H 'Content-Type: application/json' \
  -d '{
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
status_url
artifacts_url
live_mp4_url
preview_mp4_url
manifest_url
```

### Check active stream

```bash
curl -fsS 'http://192.168.29.20:8080/motion/streams/current?camera_id=c922_node2_gate' | python3 -m json.tool
```

### View from another LAN machine

During or after a motion stream:

```bash
vlc http://192.168.29.20:8080/motion/streams/<session_id>/live.mp4
```

After the session completes, the normal preview MP4 is also available:

```bash
vlc http://192.168.29.20:8080/motion/streams/<session_id>/preview.mp4
```

## Validation

Node2 must already be up:

```bash
./scripts/startup/node2_startup_steps12.sh
```

Node1 Step 12/13 services must already be healthy:

```bash
./scripts/startup/node1_startup_steps12.sh --download-yolo --run-validations
./scripts/startup/node1_startup_step13.sh
```

Run Step 14 validation on Node1:

```bash
./scripts/startup/node1_startup_step14.sh --duration-sec 60
```

For a shorter smoke test:

```bash
./scripts/startup/node1_startup_step14.sh --duration-sec 15
```

Expected final artifacts:

```text
data/datasets/<session_id>/artifacts/live.mp4
data/datasets/<session_id>/artifacts/preview.mp4
data/datasets/<session_id>/manifest.json
data/datasets/<session_id>/metadata/frames.jsonl
```

Expected API checks:

```bash
curl -fsS http://192.168.29.20:8080/capture/sessions/<session_id> | python3 -m json.tool
curl -fsS http://192.168.29.20:8080/capture/sessions/<session_id>/artifacts | python3 -m json.tool
curl -L -o live.mp4 http://192.168.29.20:8080/motion/streams/<session_id>/live.mp4
```

## Notes

- `live.mp4` is written as fragmented MP4 with ffmpeg so it can be tailed while recording.
- `preview.mp4` is generated after completion from the source JPEG frame dataset.
- The current milestone provides the Node1 API contract and Node2-style webhook path. A future enhancement can add a persistent Node2 motion watcher service that calls `/motion/events/node2` automatically.
- True low-latency production live streaming can later evolve to HLS/fMP4, RTSP restream, or WebRTC. This milestone keeps the simplest LAN-validated MP4 path first.
