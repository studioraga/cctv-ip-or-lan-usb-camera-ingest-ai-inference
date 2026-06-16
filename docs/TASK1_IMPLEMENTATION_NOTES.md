# Task1 Implementation Notes

This repository extends the working Node1/Node2 camera transport into a local-first AI CCTV service layer.

## Implemented components

1. Node1 RTP/JPEG receiver with `mjpeg_480p30`, `mjpeg_720p30`, `mjpeg_720p60`, and raw debug profile support.
2. Node2 GStreamer/V4L2 streamer controller under `agents/node2/node2_streamer_controller.py`.
3. Node2 FastAPI control agent under `services/node2_control_agent/`.
4. Node1 FastAPI API gateway under `services/node1_api_gateway/`.
5. Prometheus metrics for Node1 receiver and Node2 control service.
6. Migration-managed SQLite schema through `migrations/` and `services/common/event_db.py`.
7. Motion-event generation with event rows, JSONL records, keyframe JPGs, and MP4 clips.
8. Secure media retrieval pattern using opaque identifiers and path-containment checks.
9. Deterministic query endpoint scaffolding.
10. Qdrant adapter scaffold for future vector/event search.
11. Policy validation, systemd service templates, Docker/Prometheus artifacts, and runtime render scripts.

## Step 8/9 validated additions

The latest validation added these important operational fixes:

- `agents/node2/__init__.py` is required so `agents.node2.node2_streamer_controller` imports correctly on Node2 and in CI.
- `requirements-node1.txt` and `requirements-node2.txt` include both `httpx` and `httpx2` because service tests import Node1/Node2 FastAPI apps using current Starlette/FastAPI test dependencies.
- Node1 `.venv` must be created with `--system-site-packages` and must report OpenCV `GStreamer: YES`.
- Node2 `.venv` is intentionally isolated without `--system-site-packages`. The Jetson camera path uses GStreamer/V4L2 command-line tools, while the FastAPI control API must avoid mixing `~/.local`, apt Python packages, and venv packages. Runtime uses `PYTHONNOUSERSITE=1`.
- `scripts/validate_step9_streaming.sh` captures the validated Node1-to-Node2 control path and Node2-to-Node1 RTP data path.

## Validated end-to-end flow

```text
Node1 trusted control client
  -> POST Node2 /stream/start
  -> Node2 gst-launch-1.0 owns /dev/video0
  -> RTP/JPEG to Node1 UDP/5000
  -> Node1 receiver decodes frames through OpenCV/GStreamer
  -> metrics show ~15 FPS and increasing frames_total
  -> motion_detected events are written to JSONL and SQLite
  -> Node1 POST Node2 /stream/stop
  -> Node2 sends EOS, frees pipeline, /dev/video0 becomes available
```

## Important operational findings

| Finding | Impact | Permanent handling |
|---|---|---|
| Node1 PyPI OpenCV reported `GStreamer: NO` | Receiver could not open RTP pipeline | Node1 venv setup now validates `GStreamer: YES` |
| Manual sender and API sender cannot both own `/dev/video0` | API start can exit with rc=1 and `Device busy` | Stop manual `gst-launch` before API streaming |
| Node2 local `/stream/status` can return 403 | Policy trusts Node1, not every local caller | Query Node2 stream-control endpoints from Node1 |
| Runtime artifacts appeared in the archive | Source archives become large/non-portable | `.gitignore` and sync exclusions exclude `.venv`, DB, clips, keyframes, pycache, results |

## Next implementation direction

After this baseline, the next clean task is operational hardening and reproducibility:

1. Keep source archive clean of runtime/generated artifacts.
2. Add Step 8/9 runbook sections to README and deployment docs.
3. Preserve the venv setup rules in scripts and docs.
4. Add a repeatable validation script for API-controlled streaming.
5. Commit the validated source changes before adding object detection or model-serving features.
