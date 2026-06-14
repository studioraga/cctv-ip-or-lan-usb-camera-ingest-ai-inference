#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"; cd "$AI_CAMERA_REPO_ROOT"
NODE1_IP="${AI_CAMERA_NODE1_IP:-$(ai_camera_primary_ipv4)}"; [[ -n "$NODE1_IP" ]] || { echo 'ERROR: cannot determine Node1 IP' >&2; exit 1; }
export AI_CAMERA_NODE1_IP="$NODE1_IP"
exec "$(ai_camera_uvicorn)" services.node1_api_gateway.app:app --host "$NODE1_IP" --port "$AI_CAMERA_NODE1_API_PORT" --no-proxy-headers
