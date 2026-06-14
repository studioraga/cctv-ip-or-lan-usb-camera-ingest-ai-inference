#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
exec .venv/bin/python scripts/common/apply_migrations.py \
  --db-path "${AI_CAMERA_DB:-data/events/ai_camera.db}" \
  --migrations-dir "${AI_CAMERA_MIGRATIONS:-migrations}"
