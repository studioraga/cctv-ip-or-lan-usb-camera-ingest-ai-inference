#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
POLICY_PATH="${AI_CAMERA_POLICY:-configs/runtime/security_policy.yaml}"

[[ -x .venv/bin/python ]] || { echo "ERROR: .venv missing; run scripts/node2/install_node2_dependencies.sh"; exit 1; }
.venv/bin/python scripts/common/render_runtime_config.py --role node2 --repo-root "$REPO_ROOT"
.venv/bin/python scripts/common/validate_policy.py --policy "$POLICY_PATH"
[[ -e /dev/video0 ]] || echo "WARN: /dev/video0 is not currently present"
command -v gst-launch-1.0 >/dev/null || { echo "ERROR: GStreamer is not installed"; exit 1; }
command -v v4l2-ctl >/dev/null || { echo "ERROR: v4l2-ctl is not installed"; exit 1; }

echo "[OK] Node2 Step 1 policy and runtime prerequisites validated"
