# Step 12 — True E2E Timestamped Latency and YOLO ONNX Post-processing

Step 11 added receiver-side latency stability metrics on Node1. Step 12 addresses two remaining limitations:

1. **True sender-to-receiver correlation**: Node2 now has an opt-in timestamped JPEG/UDP transport that attaches a `frame_id`, `sender_wall_ns`, and `sender_monotonic_ns` to every camera frame. Node1 can decode those timestamps and export true sender-timestamp-to-Node1-decode metrics.
2. **YOLO ONNX post-processing**: `YoloOnnxDetector` now decodes common YOLOv5/YOLOv8-style ONNX outputs, maps boxes back to the original image, applies confidence filtering and per-class NMS, and returns detection dictionaries.

The default production transport remains `rtp`. The timestamped transport is opt-in so the existing GStreamer/RTP pipeline and Gate 4/5 validations remain compatible.

## E2E timestamped transport

### New transport mode

`agents/node2/node2_timed_jpeg_sender.py` captures MJPEG frames from `/dev/video0` through `ffmpeg`, then sends each JPEG frame to Node1 as UDP fragments using `services/common/timed_frame_protocol.py`.

Each frame carries:

- `frame_id`: monotonically increasing Node2 frame sequence
- `sender_wall_ns`: Node2 wall-clock timestamp at sender extraction/send time
- `sender_monotonic_ns`: Node2 monotonic timestamp for local sequencing/debug
- fragment index/count
- JPEG payload bytes

Node1 receives this with:

```bash
python -m agents.node1.node1_receiver_agent \
  --transport timed_jpeg_udp \
  --profile mjpeg_720p30 \
  --port 5000 \
  --metrics \
  --metrics-port 9101
```

Node1 computes:

```text
e2e_latency_ms = (node1_decode_done_wall_ns - node2_sender_wall_ns) / 1_000_000
```

This requires Node1 and Node2 clocks to be synchronized, preferably with chrony. The monotonic timestamp is intentionally not used for cross-machine latency because monotonic clocks are host-local.

### New E2E metrics

Node1 now exports these additional metrics when `--transport timed_jpeg_udp` is active:

```text
ai_camera_e2e_latency_ms
ai_camera_e2e_frame_id
ai_camera_e2e_clock_delta_ms
```

The rolling bounded-slices monitor also gains:

```text
latency_kind="e2e_latency_ms"
```

So the same Step 11 algorithm now summarizes true correlated sender-to-decode latency windows.

### Validation

Run from **Node1**:

```bash
./scripts/validate_step12_e2e_latency.sh
```

The script temporarily stops the production Node1 receiver service so it can bind UDP `5000` and metrics `9101`, starts a manual timestamped receiver, starts Node2 with `transport=timed_jpeg_udp`, checks that frames and E2E metrics increase, stops Node2, then restarts the production receiver if it was previously active.

Pass condition:

```text
[OK] frames_total increased and E2E timestamped latency metrics were exported
[OK] Step 12 E2E timestamped latency validation completed
```

## YOLO ONNX post-processing

`services/node1_inference_worker/detectors/yolo_onnx.py` now supports:

- YOLOv5-style outputs: `(1, N, 5 + classes)` with `cx,cy,w,h,obj,class_scores...`
- YOLOv8-style outputs: `(1, 4 + classes, N)` or `(1, N, 4 + classes)` with `cx,cy,w,h,class_scores...`
- Already postprocessed outputs: `(N, 6)` with `x1,y1,x2,y2,score,class_id`

The detector performs:

1. Letterbox resize with aspect-ratio preservation
2. RGB/CHW float preprocessing
3. ONNX Runtime inference
4. YOLO output normalization
5. Confidence filtering
6. Mapping boxes back to original image coordinates
7. Per-class non-maximum suppression
8. Detection dictionary output

Detection output shape:

```json
{
  "label": "person",
  "confidence": 0.87,
  "bbox_xyxy": [120.0, 64.0, 280.0, 420.0],
  "attrs": {"class_id": 0}
}
```

### YOLO validation

Run:

```bash
./scripts/validate_step12_yolo_onnx.sh
```

This always runs synthetic post-processing unit tests. If a real model is available, set:

```bash
export AI_CAMERA_YOLO_MODEL=models/object_detection/your_model.onnx
./scripts/validate_step12_yolo_onnx.sh
```

The script will load the model and run a smoke inference on a blank frame.

## Important limitations that remain

The timestamp is assigned when Node2 userspace sender extracts/sends the JPEG frame, not at the exact camera sensor exposure time. True sensor exposure timestamping would require V4L2 buffer timestamp extraction and carrying that exact timestamp in metadata. The current implementation is a practical Node2 sender-to-Node1 decode E2E measurement.

For YOLO, model-specific class names and input size should match the selected ONNX export. The generic decoder supports common YOLOv5/YOLOv8 layouts, but unusual exports may require an adapter.
