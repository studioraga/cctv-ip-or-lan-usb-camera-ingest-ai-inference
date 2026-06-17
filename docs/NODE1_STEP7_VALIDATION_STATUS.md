# Node1 Step 7 validation status and fixes

This document records the Node1-only validation and the later Step 9 receiver root-cause fix.

## Step 7 validated items

- `deploy/ai-camera.env` can point the repository to `$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference`.
- `scripts/common/detect_environment.py --json` detects Node1 IP, Python, GPU/system information, and required tools.
- `scripts/common/prepare_deployment.sh node1` renders runtime policy and node configuration.
- `configs/runtime/security_policy.yaml` validates as policy version 2.
- SQLite migrations `001_initial.sql` and `002_step1_security.sql` apply cleanly and idempotently.
- Required tables exist: `cameras`, `clips`, `events`, `media_access_audit`, `schema_migrations`.
- SQLite integrity check returns `ok`.
- Node1 API service starts as a systemd service and exposes `/health` on `192.168.29.20:8080`.

## Step 7 receiver module-launch fix

The first generated receiver unit launched a direct file path:

```ini
ExecStart=.../python agents/node1/node1_receiver_agent.py ...
```

That failed under systemd with:

```text
ModuleNotFoundError: No module named 'services'
```

Permanent fix:

```ini
ExecStart=.../python -m agents.node1.node1_receiver_agent ...
```

Also required:

```text
agents/__init__.py
agents/node1/__init__.py
agents/node2/__init__.py
```

## Step 9 receiver root cause and fix

During Step 9, Node1 receiver entered an auto-restart storm:

```text
[ERROR] Failed to open GStreamer pipeline
ExecMainStatus=1
NRestarts=116
```

Root cause:

```text
Node1 .venv OpenCV 4.13.0
GStreamer: NO
```

The receiver requires OpenCV with GStreamer enabled. The fix was to recreate Node1 `.venv` with system site packages:

```bash
sudo systemctl stop node1-ai-camera-api.service node1-ai-camera-receiver.service
mv .venv ".venv.backup-$(date +%Y%m%d-%H%M%S)"
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-node1.txt
```

Validated fixed state:

```text
OpenCV: 4.6.0
GStreamer: YES (1.24.1)
node1-ai-camera-api.service active
node1-ai-camera-receiver.service active
192.168.29.20:8080 listening
0.0.0.0:9101 listening
0.0.0.0:5000/udp bound
```

## Current Step 7/9 combined status

```text
Node1 API service                  PASS
Node1 receiver service             PASS
Node1 venv OpenCV/GStreamer        PASS
Node1 metrics endpoint             PASS
Node1 RTP receiver port            PASS
Node1 event DB and JSONL evidence  PASS
```

---

## Later status through Step 13

This file records the earlier Node1 Step 7/9 validation history. The current
working baseline has advanced to Step 13:

- Node1 API and receiver services remain operational.
- Node1 API now also serves `/ui/capture`, `/capture/sessions`, and dataset artifact endpoints.
- Node1 runs the Prometheus/Grafana Docker stack for the `AI Camera Capture Session Demo` dashboard.
- Step 13 capture sessions write source-JPEG datasets under `data/datasets/{session_id}/`.

Use `docs/STEP13_GRAFANA_CAPTURE_DATASET.md` for the current demo runbook.
