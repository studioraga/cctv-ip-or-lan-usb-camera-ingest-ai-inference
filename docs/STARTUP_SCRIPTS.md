# Startup scripts for Node1 and Node2 through Step 12

These scripts turn the README fresh-start commands into repeatable node-local startup flows.
They are intentionally idempotent: re-running them should regenerate runtime config, reinstall systemd units, daemon-reload, enable, restart, and then verify that services are running from the current checkout.

## Order of operation

Run Node2 first, then Node1.

```bash
# Node2 / Jetson
cd "$HOME/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
./scripts/startup/node2_startup_steps12.sh --install-deps

# Node1 / workstation
cd "$HOME/dev/pub/ai-sys1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
./scripts/startup/node1_startup_steps12.sh --install-deps --download-yolo --run-validations
```

After the first dependency install, normal restart/validation becomes shorter:

```bash
# Node2
./scripts/startup/node2_startup_steps12.sh

# Node1
./scripts/startup/node1_startup_steps12.sh --run-validations
```

## Required environment

Each node needs its own `deploy/ai-camera.env`.
Create it from the example when missing:

```bash
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Recommended minimum values:

Node1:

```text
AI_CAMERA_NODE_ROLE=node1
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
```

Node2:

```text
AI_CAMERA_NODE_ROLE=node2
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
```

Leave `AI_CAMERA_REPO_ROOT=` blank unless you intentionally need an absolute override. The startup scripts force the current checkout path when installing systemd units so stale paths such as an older `mig1` checkout do not remain in service commands.

## What the scripts validate

Node2 startup checks:

- `.venv` exists, or it builds it when `--install-deps` is used.
- camera capabilities are printed when `v4l2-ctl` and `/dev/video0` are present.
- runtime config and policy are generated.
- tests pass through `prepare_deployment.sh node2`.
- `node2-camera-control-agent.service` is installed, reloaded, enabled, restarted, and healthy.
- the running systemd command path includes the current checkout path.

Node1 startup checks:

- `.venv` exists, or it builds it when `--install-deps` is used.
- when `--download-yolo` is used, `models/object_detection/yolo11n.onnx` is downloaded and `AI_CAMERA_YOLO_MODEL` is pinned in `deploy/ai-camera.env`.
- runtime config, policy, migrations, and tests pass through `prepare_deployment.sh node1`.
- `node1-ai-camera-api.service` and `node1-ai-camera-receiver.service` are installed, reloaded, enabled, restarted, and healthy.
- Node1 receiver metrics on port `9101` is reachable.
- Node2 health is reachable from Node1.
- the running systemd command path includes the current checkout path.
- the receiver unit contains `--no-exit-on-no-frames`.

When Node1 is run with `--run-validations`, it also runs:

```bash
./scripts/validate_step9_streaming.sh
./scripts/validate_step11_latency_monitoring.sh
./scripts/validate_step12_e2e_latency.sh
./scripts/validate_step12_yolo_onnx.sh
```

To force the real YOLO ONNX smoke in the same flow, run Node1 with both flags:

```bash
./scripts/startup/node1_startup_steps12.sh --download-yolo --run-validations
```

## Logs

Startup logs are written under:

```text
results/startup/
```

Those logs are intentionally ignored by git and can be attached for review after a run.

## Step 13 Node1 observability/capture startup

After Node2 and Node1 Step 12 services are healthy, start the Step 13 Docker
observability stack from Node1:

```bash
./scripts/startup/node1_startup_step13.sh
```

To also run a bounded capture-session dataset validation in the same flow:

```bash
./scripts/startup/node1_startup_step13.sh --capture-test
```

The Step 13 startup script renders `configs/runtime/prometheus.yml` before
starting Docker Compose. This is required because the Compose file bind-mounts
that generated file into the Prometheus container.

Step 16 hardening binds Prometheus, Grafana, and Qdrant to localhost by default
with `AI_CAMERA_OBSERVABILITY_BIND=127.0.0.1`. The startup script therefore
performs health checks through `127.0.0.1`. To open Grafana from another LAN
machine, set `AI_CAMERA_OBSERVABILITY_BIND=0.0.0.0` or the Node1 LAN IP and set
a strong `GRAFANA_ADMIN_PASSWORD` in `deploy/ai-camera.env`. Grafana stores
admin credentials in the persistent `grafana_storage` Docker volume, so changing
the env file after first startup does not update the stored password by itself.
The startup script keeps `AI_CAMERA_GRAFANA_SYNC_ADMIN_PASSWORD=1` by default
and resets the Grafana admin password to the env-file value before authenticated
API dashboard checks.

If `docker compose up` was run before rendering the file, Docker may have
created `configs/runtime/prometheus.yml` as a directory. The render script
repairs that specific stale path and writes the expected file.


## Step 14 motion-triggered live MP4 startup

After Node2 Step 12 and Node1 Step 12/13 are healthy:

```bash
./scripts/startup/node1_startup_step14.sh --duration-sec 60
```

This posts a Node2-style motion event to Node1, starts a bounded capture session,
creates `artifacts/live.mp4` while recording, creates `artifacts/preview.mp4` after
completion, and prints the LAN viewer URLs.

## Step 15 Node2 motion watcher startup

Step 15 adds `node2-motion-watcher.service` for Option A motion-triggered capture. The watcher owns `/dev/video0` during idle detection, releases it before Node1 starts the bounded capture session, then reopens it after Node1 reports session completion.

Install dependencies and start the watcher on Node2:

```bash
./scripts/startup/node2_startup_step15.sh --install-deps
```

Install the service but do not enable it yet:

```bash
./scripts/startup/node2_startup_step15.sh --no-enable-watcher
```

Validate without camera/network effects:

```bash
./scripts/validate_step15_node2_motion_trigger.sh --static-only
```

Validate the Node2-to-Node1 trigger path with a synthetic person detection:

```bash
./scripts/validate_step15_node2_motion_trigger.sh --synthetic-trigger
```
