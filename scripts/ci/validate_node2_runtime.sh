#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[CI:NODE2] Controller import and profile commands"
python3 - <<'PY'
from agents.node2.node2_streamer_controller import PROFILES, build_gstreamer_command
for profile in sorted(PROFILES):
    cmd = build_gstreamer_command(profile, '192.168.29.20', 5000, '/dev/video0')
    print(profile, '=>', ' '.join(cmd))
print('Node2 profiles OK')
PY

echo "[CI:NODE2] FastAPI control app import"
python3 - <<'PY'
import services.node2_control_agent.app as app
print('Node2 control app import OK:', app.app.title)
PY

echo "[CI:NODE2] Optional camera presence"
if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-devices || true
else
  echo "v4l2-ctl not installed; skipping camera probe"
fi

echo "[CI:NODE2] Runtime validation PASS"
