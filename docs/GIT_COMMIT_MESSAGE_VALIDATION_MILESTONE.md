# Suggested Git commit message for Step 8/9 validation milestone

```text
Stabilize Node1/Node2 CCTV streaming deployment

- Preserve Node1 OpenCV/GStreamer runtime by requiring venv creation with --system-site-packages
- Add validation failure when Node1 cv2 does not report GStreamer: YES
- Add Node2 package marker for streamer controller imports
- Add missing httpx/httpx2 dependencies for Node1 and Node2 runtime tests
- Improve Node1 and Node2 venv setup scripts with explicit dependency checks
- Strengthen Node1/Node2 runtime CI validation scripts
- Add repeatable Step 9 API-controlled streaming validation script
- Update portable deployment, architecture, venv, CI/CD, and validation docs
- Document root causes for GStreamer pipeline open failure, device busy, and policy 403 cases
- Validate Node2 API-controlled RTP/JPEG streaming into Node1 receiver
- Confirm receiver metrics, motion events, clip/keyframe metadata, and SQLite evidence
```

Short subject option:

```text
Stabilize API-controlled Node1/Node2 camera streaming
```

## Validation evidence summary

```text
Node1 API service                 PASS
Node1 receiver service            PASS
Node1 OpenCV GStreamer            PASS
Node2 control service             PASS
Node2 /stream/start               PASS
Node2 /stream/status from Node1   PASS
Node1 receiver FPS                PASS (~15 FPS)
Node1 frames_total                PASS (increasing)
Node1 JSONL evidence              PASS
Node1 SQLite motion events        PASS
Node2 /stream/stop                PASS
Node2 camera process cleanup      PASS
```

## Files expected in this commit

```text
README.md
docs/ARCHITECTURE.md
docs/CI_CD_VALIDATION_PLAN.md
docs/GIT_COMMIT_MESSAGE_VALIDATION_MILESTONE.md
docs/NODE1_STEP7_VALIDATION_STATUS.md
docs/PORTABLE_DEPLOYMENT.md
docs/STEP1_MIGRATIONS_POLICY_MEDIA_SECURITY.md
docs/TASK1_IMPLEMENTATION_NOTES.md
docs/VENV_SETUP.md
requirements-node1.txt
requirements-node2.txt
agents/node2/__init__.py
scripts/node1/setup_node1_venv.sh
scripts/node2/setup_node2_venv.sh
scripts/ci/validate_node1_runtime.sh
scripts/ci/validate_node2_runtime.sh
scripts/common/sync_repo_to_node2.sh
scripts/validate_step9_streaming.sh
```

## Step 10.2 commit message

```text
Harden reproducible Node1/Node2 CCTV deployment validation

- Add Step 10 reproducible deployment validation script
- Preserve source hygiene checks for clean archives and syncs
- Keep Node1 OpenCV/GStreamer validation as a mandatory runtime gate
- Validate Node1 and Node2 deployment preparation from generated runtime config
- Add service health checks for Node1 API, Node1 receiver, and Node2 control agent
- Keep API-controlled Step 9 streaming as an optional Node1-launched hardware gate
- Document operational hardening, failure signatures, and pass criteria
```


- `docs/STEP10_OPERATIONAL_HARDENING.md`

- `scripts/validate_step10_reproducible_deployment.sh`

---

# Suggested Git commit message for Step 13 Grafana capture-session milestone

```text
Add Grafana capture sessions and dataset artifacts

Implement Step 13 for the local AI camera demo.

This adds a Grafana-visible, Node1 API-driven bounded capture-session workflow
that uses the Step 12 timestamped JPEG/UDP transport to capture source JPEG
frames from Node2 and store them as Node1 datasets for later analysis.

Functional features now working:
- Node1 `/ui/capture` form for demo-triggered captures.
- Node1 `/capture/sessions` API with duration enforcement up to 7200 seconds.
- Node1 capture-session orchestration that starts/stops Node2 automatically.
- Dedicated capture UDP port `AI_CAMERA_CAPTURE_UDP_PORT=5001` separate from
  the production RTP receiver on UDP 5000.
- Node2 `timed_jpeg_udp` capture path carrying `frame_id`, `sender_wall_ns`,
  and `sender_monotonic_ns` metadata.
- Source-JPEG dataset writer under `data/datasets/{session_id}/frames`.
- Per-frame `metadata/frames.jsonl` with timestamps, E2E latency, JPEG size,
  fragment count, SHA-256, and write latency.
- Dataset artifacts: `manifest.json`, `metrics_summary.json`, `report.md`,
  and best-effort `preview.mp4`.
- SQLite migration `003_capture_sessions.sql` for capture sessions and artifacts.
- Prometheus metrics for capture active state, frames, bytes, dropped frames,
  E2E latency, write latency, disk free, and errors.
- Grafana/Prometheus Docker stack with provisioned Prometheus datasource and
  `AI Camera Capture Session Demo` dashboard.
- Correct Docker Compose relative mounts for rendered Prometheus config and
  Grafana provisioning/dashboard files.
- Validation scripts for Grafana stack provisioning and live capture-session
  dataset generation.

Validated in the Node1/Node2 LAN lab:
- Node1 static validation passed.
- Node1 pytest passed with 27 tests.
- Grafana stack validation passed.
- Grafana dashboard appears under `AI Camera / AI Camera Capture Session Demo`.
- UI-triggered 30-second capture completed with 437 source JPEG frames,
  87,274,343 bytes, zero dropped frames, avg E2E latency around 18.19 ms,
  and generated report/preview artifacts.
- Automated Step 13 capture validation completed with Node2 stopped cleanly.

Notes:
- Production receiver remains `AI_CAMERA_TRANSPORT=rtp` on UDP 5000.
- Step 13 capture sessions use `transport=timed_jpeg_udp` on UDP 5001.
- Runtime datasets, DB files, generated configs, and validation results should
  not be committed.
```
