#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
source .venv/bin/activate
mkdir -p data/events
export AI_CAMERA_DB="${AI_CAMERA_DB:-data/events/ai_camera.db}"
export NODE2_URL="${NODE2_URL:-http://192.168.29.188:8082}"
exec uvicorn services.node1_api_gateway.app:app --host "${HOST:-192.168.29.20}" --port "${PORT:-8080}"
