# Step 15: Node2 YOLO Motion Trigger for Node1-Managed Live MP4 Capture

Step 15 implements **Option A** for motion-triggered capture:

```text
Node2 watcher owns /dev/video0 while idle
  -> cheap frame-difference motion gate
  -> YOLO ONNX confirmation for person/object classes
  -> release /dev/video0
  -> POST Node1 /motion/events/node2
  -> Node1 starts timed_jpeg_udp capture through Node2 control agent
  -> Node1 writes source JPEG dataset + live.mp4 + preview.mp4
  -> Node2 watcher waits for Node1 session completion
  -> Node2 watcher cooldown
  -> Node2 watcher reopens /dev/video0 and resumes watching
```

This keeps **Node1 as the session authority**. Node2 only detects and requests a session.

## Why Option A first

Option A avoids the complexity of a GStreamer `tee` pipeline. Only one process owns the camera at a time:

```text
Idle watch mode:        node2-motion-watcher owns /dev/video0
Capture/live session:   node2_timed_jpeg_sender owns /dev/video0
After session:          node2-motion-watcher owns /dev/video0 again
```

This is the safest first milestone before moving to Option B.

## New files

```text
services/node2_motion_watcher/watcher.py
agents/node2/node2_motion_watcher.py
scripts/node2/run_node2_motion_watcher.sh
scripts/startup/node2_startup_step15.sh
scripts/validate_step15_node2_motion_trigger.sh
systemd/templates/node2-motion-watcher.service.in
services/common/detectors/yolo_onnx.py
services/common/detectors/motion.py
```

## Node2 watcher state machine

```text
IDLE_WATCHING
  Camera is open and sampled at AI_CAMERA_NODE2_WATCHER_SAMPLE_FPS.

MOTION_CANDIDATE
  Frame-difference motion score exceeds AI_CAMERA_NODE2_WATCHER_MOTION_THRESHOLD.

YOLO_CONFIRMATION
  YOLO ONNX runs only after the cheap motion gate fires.
  Detections are filtered by AI_CAMERA_NODE2_WATCHER_CLASSES.

TRIGGER_SENT
  Watcher releases the camera and posts /motion/events/node2 to Node1.

SESSION_ACTIVE
  Node1 starts the bounded capture and commands Node2 control agent to stream.
  Watcher polls Node1 session status until the session is no longer pending/running.

COOLDOWN
  Watcher waits AI_CAMERA_NODE2_WATCHER_COOLDOWN_SEC and then reopens the camera.
```

## Important environment variables

```bash
AI_CAMERA_MOTION_STREAM_DURATION_SEC=60
AI_CAMERA_NODE2_WATCHER_SAMPLE_FPS=5
AI_CAMERA_NODE2_WATCHER_MOTION_THRESHOLD=12
AI_CAMERA_NODE2_WATCHER_CANDIDATE_WINDOW=5
AI_CAMERA_NODE2_WATCHER_REQUIRED_CONFIRMATIONS=2
AI_CAMERA_NODE2_WATCHER_COOLDOWN_SEC=20
AI_CAMERA_NODE2_WATCHER_REQUIRE_YOLO=1
AI_CAMERA_NODE2_WATCHER_YOLO_MODEL=models/object_detection/yolo11n.onnx
AI_CAMERA_NODE2_WATCHER_YOLO_INPUT_SIZE=640
AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE=0.45
AI_CAMERA_NODE2_WATCHER_YOLO_IOU=0.45
AI_CAMERA_NODE2_WATCHER_CLASSES=person,bicycle,car,motorcycle,bus,truck,cat,dog,backpack,suitcase
```

For product validation, keep `AI_CAMERA_NODE2_WATCHER_REQUIRE_YOLO=1` so motion alone does not trigger capture. For static validation without a model, use `--no-require-yolo` or `--static-only`.

## Static validation

Run this anywhere after dependencies are available:

```bash
./scripts/validate_step15_node2_motion_trigger.sh --static-only
```

This validates imports, payload construction, debouncer behavior, and synthetic payload formatting. It does not contact Node1/Node2.

## Synthetic network validation

Run this on Node2 after Node1 API and Node2 control agent are started:

```bash
./scripts/validate_step15_node2_motion_trigger.sh --synthetic-trigger
```

This posts a synthetic `person` detection to Node1. Node1 should then start a real bounded capture session and call Node2 `/stream/start` with `transport=timed_jpeg_udp`.

## Manual watcher run

```bash
./scripts/node2/run_node2_motion_watcher.sh --one-shot
```

For a dry-run synthetic payload:

```bash
./scripts/node2/run_node2_motion_watcher.sh \
  --synthetic-trigger \
  --dry-run \
  --no-require-yolo
```

For testing motion-only behavior while the model setup is still being validated:

```bash
./scripts/node2/run_node2_motion_watcher.sh \
  --one-shot \
  --no-require-yolo
```

## Systemd startup

```bash
./scripts/startup/node2_startup_step15.sh --install-deps
```

To install but not start the watcher:

```bash
./scripts/startup/node2_startup_step15.sh --no-enable-watcher
```

## Node1 event payload extension

Step 15 extends the Node1 `/motion/events/node2` payload with optional trigger evidence:

```json
{
  "detections": [
    {
      "label": "person",
      "confidence": 0.9,
      "bbox_xyxy": [220.0, 90.0, 640.0, 710.0],
      "class_id": 0
    }
  ],
  "trigger_frame_id": 12345,
  "trigger_wall_ns": 1782300000000000000,
  "cooldown_sec": 20.0
}
```

Node1 stores this trigger evidence in the event `attrs` JSON and includes a compact detection summary in the capture-session notes.

## Expected Step 15 validation behavior

After a real detection:

```text
Node2 watcher log:
  motion_score=... detections=[person ...]
  Posting Node2 motion event to Node1
  Node1 capture session cap_... status=running
  Node1 capture session cap_... status=completed
  Cooldown ... before returning to watch mode

Node1 artifacts:
  data/datasets/<session_id>/manifest.json
  data/datasets/<session_id>/frames.jsonl
  data/datasets/<session_id>/artifacts/live.mp4
  data/datasets/<session_id>/artifacts/preview.mp4
  data/datasets/<session_id>/artifacts/report.md
```

## Known limitation before Option B

There can be a very small gap between watcher camera release and Node2 timed JPEG sender startup. That is acceptable for Option A validation. Option B will remove this gap by using a single long-lived GStreamer pipeline with a tee branch.

## Step 15A decoder and watcher fixes

The watcher depends on the shared YOLO ONNX decoder.  YOLOv8/YOLO11 COCO ONNX
models commonly emit `(1, 84, N)` or `(1, N, 84)` tensors where the first four
columns are `cx, cy, w, h` and the remaining 80 columns are class scores.  There
is no separate objectness column.  The decoder now infers YOLOv8/YOLO11 versus
YOLOv5 by tensor column count and optional class-name count instead of using
score-value heuristics.  This avoids treating class-0 `person` score as YOLOv5
objectness.

For Node2 tuning, the watcher CLI now supports direct overrides so you do not
need to edit `deploy/ai-camera.env` during validation:

```bash
./scripts/node2/run_node2_motion_watcher.sh --one-shot \
  --yolo-confidence 0.25 \
  --motion-threshold 8 \
  --required-confirmations 1 \
  --candidate-window 3 \
  --sample-fps 5 \
  --log-level DEBUG
```

`runtime_env.sh` now preserves `AI_CAMERA_*` variables already exported by the
caller before loading `deploy/ai-camera.env`.  That means this works as intended:

```bash
AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE=0.25 \
AI_CAMERA_NODE2_WATCHER_MOTION_THRESHOLD=8 \
./scripts/node2/run_node2_motion_watcher.sh --one-shot --log-level DEBUG
```

At `DEBUG` level the watcher logs raw YOLO detections before label filtering:

```text
raw_yolo_detections_count=...
raw_yolo_detections=[...]
```

## Standalone C922 + YOLO smoke test

Before validating the full watcher, run a one-frame C922 detector smoke test on
Node2 with someone clearly visible in front of the camera:

```bash
AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE=0.25 \
./scripts/node2/test_c922_yolo_frame.sh --image /tmp/c922_yolo_test.jpg
```

Expected success signal:

```json
{
  "interesting_detection_count": 1,
  "interesting_detections": [
    {"label": "person", "confidence": 0.7, "class_id": 0}
  ]
}
```

If `raw_detection_count` is positive but `interesting_detection_count` is zero,
check `AI_CAMERA_NODE2_WATCHER_CLASSES`.  If both are zero, lower
`AI_CAMERA_NODE2_WATCHER_YOLO_CONFIDENCE` temporarily and confirm the model path.

## Real watcher one-shot validation

After the one-frame detector smoke test succeeds, validate the full Option A
state machine:

```bash
./scripts/node2/run_node2_motion_watcher.sh --one-shot \
  --yolo-confidence 0.25 \
  --motion-threshold 8 \
  --required-confirmations 1 \
  --candidate-window 3 \
  --sample-fps 5 \
  --log-level DEBUG
```

The watcher should release `/dev/video0`, post `/motion/events/node2` to Node1,
wait for Node1 session completion, and then exit because `--one-shot` was used.

## LAN live MP4 viewer helper

From Node1 or another LAN Linux machine with access to Node1 API:

```bash
./scripts/node1/watch_motion_live_mp4_vlc.sh \
  --node1-url http://192.168.29.20:8080 \
  --camera-id c922_node2_gate
```

The script polls `/motion/streams/current` until a session is active, then opens:

```text
http://192.168.29.20:8080/motion/streams/<session_id>/live.mp4
```

After completion, use `--preview` to open the finalized MP4 artifact:

```bash
./scripts/node1/watch_motion_live_mp4_vlc.sh \
  --node1-url http://192.168.29.20:8080 \
  --camera-id c922_node2_gate \
  --preview
```
