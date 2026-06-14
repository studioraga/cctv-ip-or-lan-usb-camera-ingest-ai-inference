# Step 1 implementation: migrations, fail-closed policy, and secure media access

## 1. Scope

This implementation completes the first prerequisite for later agent, retrieval, and domain-model work:

1. migration-managed SQLite schema shared by the Node1 receiver and API;
2. strict allow-list policy enforcement on Node1 and Node2;
3. clip/keyframe retrieval by opaque database identifier, not caller-supplied paths;
4. canonical path containment and symlink-escape protection;
5. media-access auditing;
6. setup, validation, and test scripts;
7. hardened systemd examples;
8. validated Node1/Node2 API-controlled streaming evidence chain.

The receiver writes event and clip records through a shared `EventDB` access layer. Motion events can create JSONL entries, SQLite rows, keyframes, and MP4 clips.

## 2. Repository layout

```text
migrations/
├── 001_initial.sql
└── 002_step1_security.sql

services/common/
├── event_db.py
├── migrations.py
├── path_security.py
└── policy.py

services/node1_api_gateway/
├── app.py
└── schemas.py

services/node2_control_agent/
├── app.py
└── streamer_service.py

agents/node1/
└── node1_receiver_agent.py

agents/node2/
├── __init__.py
└── node2_streamer_controller.py

scripts/common/
├── apply_migrations.py
├── prepare_deployment.sh
├── render_runtime_config.py
├── sync_repo_to_node2.sh
└── validate_policy.py

scripts/ci/
├── validate_static.sh
├── validate_node1_runtime.sh
├── validate_node2_runtime.sh
└── validate_portability.sh

scripts/validate_step9_streaming.sh
```

## 3. Database migration design

Migrations replace ad hoc table creation. `services/common/migrations.py` records applied migration IDs and hashes in `schema_migrations`, making repeated deployment idempotent.

Validated behavior:

```text
[OK] Database is already at the latest migration
SQLite integrity_check: ok
Required tables: cameras, clips, events, media_access_audit, schema_migrations
```

## 4. Policy design

Runtime policy is rendered from `deploy/ai-camera.env` into `configs/runtime/security_policy.yaml`. Node2 validates each start request:

- trusted control-client IP;
- camera ID;
- allowed profile;
- allowed device;
- allowed target Node1 IP and RTP port.

This explains the expected behavior where `GET /health` works from Node2 itself but `/stream/status` can return 403 unless the caller is in the trusted control-client allow-list.

## 5. Secure media access

Media paths are produced by the receiver and stored in SQLite. API callers should use opaque IDs such as `event_id` or `clip_id`; the API must not accept arbitrary filesystem paths. `path_security.py` enforces canonical containment under configured media roots.

## 6. Validated Step 9 evidence chain

During the validated API-controlled stream:

```text
Node2 /stream/start returned running=true
Node1 receiver FPS stayed around 14.9-15.1
Node1 frames_total increased continuously
Node1 JSONL recorded receiver_fps and motion_detected events
Node1 SQLite contained latest motion_detected events
Node2 /stream/stop returned stopped
Node2 gst-launch exited through EOS and freed the camera device
```

Evidence files:

```text
results/node1/events.jsonl
data/events/ai_camera.db
data/keyframes/*.jpg
data/clips/c922_node2_gate/YYYY-MM-DD/*.mp4
results/step9/node1_step9_final_validation.txt
results/step9/node2_step9_final_validation.txt
```

Generated evidence files are runtime artifacts and should not be committed unless intentionally preserving a benchmark fixture.

## 7. Validation commands

```bash
./scripts/common/prepare_deployment.sh node1
./scripts/common/prepare_deployment.sh node2
./scripts/ci/validate_node1_runtime.sh
./scripts/ci/validate_node2_runtime.sh
./scripts/validate_step9_streaming.sh
```

## 8. Known troubleshooting points

| Symptom | Cause | Fix |
|---|---|---|
| Node1 receiver restart storm | `.venv` OpenCV has `GStreamer: NO` | Recreate Node1 venv with `--system-site-packages` |
| Node2 API stream exits rc=1 | Camera busy or bad GStreamer negotiation | Stop manual sender; check Node2 journal |
| `403` on `/stream/status` from Node2 | Node2 not trusted as control client | Query from Node1 or update policy intentionally |
| Clip/keyframe request path rejected | Path containment enforcement working | Use clip/event IDs through API |
