#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
: "${AI_CAMERA_NODE1_IP:?}" "${AI_CAMERA_NODE2_IP:?}"
envsubst < "$REPO_ROOT/docker/prometheus.yml" > "$REPO_ROOT/configs/runtime/prometheus.yml"
echo "[OK] generated configs/runtime/prometheus.yml"
