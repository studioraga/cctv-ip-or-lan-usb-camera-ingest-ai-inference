# Step 11 — Video frame latency monitoring with bounded slices

## Purpose

This step adds latency-stability monitoring to the Node1/Node2 AI camera pipeline.
The goal is not just to know that frames are arriving. The goal is to detect
whether frame timing remains stable enough for real-time CCTV AI inference.

For a latency sequence such as:

```text
[22, 24, 23, 25, 40, 41, 39]
```

with threshold `5 ms`, a window is stable when:

```text
max_latency_ms - min_latency_ms <= 5
```

The bounded-slices count tells us how many contiguous periods remain inside that
stability envelope.

## Why bounded slices fit video latency

The pattern is useful for camera streams because each new frame extends a time
series. We need to know whether a recent rolling window is stable without
re-scanning every historical sample. The implementation uses monotonic deques,
so each sample is inserted and removed at most once for O(N) batch analysis.

Useful signals include:

```text
frame_gap_ms
capture_read_ms
capture_queue_wait_ms
future: inference_ms
future: end_to_end_frame_ms after Node2 sender timestamps are added
```

## Current measurement scope

The current RTP/JPEG stream does not carry sender frame IDs or Node2 sender
monotonic timestamps. Therefore Step 11 intentionally measures **Node1-local**
receiver signals:

| Signal | Meaning |
|---|---|
| `frame_gap_ms` | Time between accepted frames in the Node1 main loop |
| `capture_read_ms` | Time spent inside OpenCV `VideoCapture.read()` in the capture worker |
| `capture_queue_wait_ms` | Time between capture-worker read completion and Node1 main-loop consumption |

These are valid stability metrics for receiver-side frame cadence, decode/read
behavior, and queueing. They are not yet true Node2-capture-to-Node1-end-to-end
latency.

## Source files

```text
services/common/bounded_slices.py              # O(N) bounded-slices algorithms
agents/node1/node1_receiver_agent.py           # rolling latency monitors + metrics
scripts/validate_step11_latency_monitoring.sh  # Node1-driven validation gate
tests/unit/test_bounded_slices.py              # algorithm and monitor tests
```

## Receiver arguments

```text
--latency-monitor / --no-latency-monitor
--latency-threshold-ms 5.0
--latency-window-samples 120
```

Defaults are intentionally enabled so the systemd receiver produces Step 11
metrics without changing the unit file.

## JSONL output

Every receiver report interval writes one `latency_window` event per latency
kind:

```json
{
  "event": "latency_window",
  "camera_id": "c922_node2_gate",
  "profile": "mjpeg_720p30",
  "latency_kind": "frame_gap_ms",
  "threshold_ms": 5.0,
  "sample_count": 120,
  "min_ms": 31.8,
  "max_ms": 35.9,
  "variation_ms": 4.1,
  "bounded_slice_count": 7260,
  "longest_stable_window": 120,
  "latest_stable_window": 120,
  "violation": false
}
```

## Prometheus metrics

```text
ai_camera_frame_gap_ms
ai_camera_capture_read_ms
ai_camera_capture_queue_wait_ms
ai_camera_latency_window_samples
ai_camera_latency_window_min_ms
ai_camera_latency_window_max_ms
ai_camera_latency_window_variation_ms
ai_camera_latency_bounded_slice_count
ai_camera_latency_longest_stable_window
ai_camera_latency_latest_stable_window
ai_camera_latency_window_violation
ai_camera_latency_window_violations_total
```

## Validation

Run from Node1 because Node1 is the trusted control client for Node2:

```bash
source .venv/bin/activate
./scripts/validate_step11_latency_monitoring.sh
```

The script:

1. checks Node1 and Node2 health,
2. starts Node2 streaming to Node1,
3. samples Node1 Prometheus metrics,
4. verifies frames increase,
5. verifies bounded-slices latency metrics are exported,
6. stops the Node2 stream.

## Pass criteria

```text
Node1 API healthy
Node2 control API healthy
Node2 stream starts from Node1
Node1 frames_total increases
ai_camera_latency_bounded_slice_count appears
Node2 stream stops cleanly
```

## Next improvement

For true end-to-end latency, add a sender timestamp and frame ID on Node2 and
carry it to Node1. Then compute:

```text
Node1_receive_monotonic_ns - Node2_send_monotonic_ns
```

This requires robust clock-sync validation or same-clock timestamp transport
semantics. Until then, Step 11 reports receiver-side stability only.
