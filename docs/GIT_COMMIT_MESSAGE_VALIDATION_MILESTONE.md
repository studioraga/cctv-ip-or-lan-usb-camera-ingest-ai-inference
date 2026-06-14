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
