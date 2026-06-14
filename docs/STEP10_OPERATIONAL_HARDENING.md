# Step 10.2: operational hardening and reproducible deployment validation

Step 10.2 makes the validated Step 8/9 Node1/Node2 deployment repeatable. The goal is to prevent a working lab from depending on hidden local state such as copied virtual environments, stale runtime configs, or manual GStreamer commands.

## Hardening goals

1. Keep the source archive clean: no `.venv`, backup venvs, pycache, SQLite runtime DBs, generated clips, keyframes, or transient logs.
2. Preserve the Node1 OpenCV/GStreamer rule: Node1 `.venv` must be created with `--system-site-packages` and must report `GStreamer: YES`.
3. Preserve Node2 importability: `agents/node2/__init__.py` must exist and `httpx`/`httpx2` must be available.
4. Make deployment generation idempotent: runtime config rendering, policy validation, and migrations should pass repeatedly.
5. Validate systemd services after install: Node1 API, Node1 receiver, and Node2 control agent must remain active.
6. Validate the end-to-end streaming gate from Node1: Node1 starts Node2 stream, Node2 sends RTP/JPEG, Node1 metrics increase, Node1 stops Node2 stream.

## Reproducible validation script

Run static/source validation from any checkout:

```bash
SOURCE_HYGIENE=1 ./scripts/validate_step10_reproducible_deployment.sh all
```

Run Node1 validation on Node1:

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
source .venv/bin/activate
RUN_PREPARE=1 ./scripts/validate_step10_reproducible_deployment.sh node1
```

Run Node2 validation on Node2:

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
source .venv/bin/activate
RUN_PREPARE=1 ./scripts/validate_step10_reproducible_deployment.sh node2
```

Run full API-controlled stream validation from Node1:

```bash
RUN_STREAM=1 ./scripts/validate_step10_reproducible_deployment.sh node1
```

The streaming validation must be started from Node1 because policy treats Node1 as the trusted control client for Node2 stream lifecycle endpoints. A direct Node2 call to `/stream/status` may return `403` unless Node2 is explicitly added as an authorized control client.

## Pass gate

```text
Static validation                        PASS
Source hygiene                           PASS
Node1 OpenCV GStreamer                   PASS
Node1 prepare_deployment                 PASS
Node1 API service and health             PASS
Node1 receiver service and metrics       PASS
Node2 prepare_deployment                 PASS
Node2 control service and health         PASS
Node2 camera process cleanup             PASS
API-controlled Step 9 stream validation  PASS
Evidence JSONL/SQLite validation         PASS
```

## Known operational failure signatures

| Symptom | Root cause | Fix |
|---|---|---|
| `Failed to open GStreamer pipeline` on Node1 | Node1 `.venv` imported PyPI OpenCV with `GStreamer: NO` | Recreate Node1 `.venv` using `python3 -m venv --system-site-packages .venv` |
| Node2 API stream exits `rc=1` | `/dev/video0` already owned by manual `gst-launch` | Stop manual sender before API streaming |
| Node2 local `/stream/status` returns `403` | Policy authorizes Node1 as stream controller | Query stream endpoints from Node1 or update policy intentionally |
| Node1 metrics unavailable | Receiver crashed or wrong OpenCV backend | Check `systemctl status`, `journalctl`, `cv2.getBuildInformation()` |
| Runtime artifacts appear in source archive | Archive created from live repo without exclusions | Use `.gitignore`/sync exclusions and run `SOURCE_HYGIENE=1` validation |

## Commit boundary

This milestone should be committed before adding object detection, model-serving, vector search, or agent orchestration. Step 10.2 is the reproducible deployment baseline.
