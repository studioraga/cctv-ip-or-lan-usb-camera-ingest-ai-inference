# Step 9 source review summary

This archive was reviewed after the validated Node1/Node2 Step 8 and Step 9 bring-up.

## Confirmed/persisted fixes

- Node2 package marker: `agents/node2/__init__.py`.
- Node1 dependency fix: `requirements-node1.txt` includes `httpx` and `httpx2`.
- Node2 dependency fix: `requirements-node2.txt` includes `httpx` and `httpx2`.
- Node1 venv setup now enforces OpenCV `GStreamer: YES` and documents the `--system-site-packages` rule.
- Node2 venv setup validates FastAPI, Prometheus, `httpx`, `httpx2`, and the GStreamer command builder.
- CI runtime scripts were strengthened for Node1 and Node2.
- Static CI command generation bug was fixed by importing `os`.
- Source sync excludes `.venv`, backup venvs, pycache, results, SQLite DB files, clips, and keyframes.
- `scripts/validate_step9_streaming.sh` was added to repeat the Node1-authorized API-controlled streaming validation.
- README and requested docs were updated to reflect the final validated Step 8/9 architecture and operational runbook.

## Validated Step 9 result represented by this source

```text
Node1 API active on 192.168.29.20:8080
Node1 receiver active on UDP/5000 and metrics :9101
Node1 OpenCV/GStreamer fixed through system-site-packages venv
Node2 control active on 192.168.29.188:8082
Node2 API-controlled stream start/status/stop works from Node1
Node1 receives ~15 FPS, frames_total increases, and motion evidence is stored
```

## Runtime artifacts removed from this clean source archive

- `.venv/`
- `.venv.backup-*/`
- `__pycache__/`
- `*.pyc`
- generated `results/` logs
- SQLite DB/WAL/SHM files
- generated MP4 clips
- generated JPG keyframes
