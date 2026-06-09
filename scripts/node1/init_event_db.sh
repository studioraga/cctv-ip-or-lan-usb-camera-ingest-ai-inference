#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
source .venv/bin/activate
python -m services.node1_event_indexer.indexer --db-path "${AI_CAMERA_DB:-data/events/ai_camera.db}"
