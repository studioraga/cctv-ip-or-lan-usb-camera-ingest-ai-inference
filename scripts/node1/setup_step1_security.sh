#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"

DB_PATH="${AI_CAMERA_DB:-data/events/ai_camera.db}"
POLICY_PATH="${AI_CAMERA_POLICY:-configs/runtime/security_policy.yaml}"

[[ -x .venv/bin/python ]] || { echo "ERROR: .venv missing; run scripts/node1/install_node1_dependencies.sh"; exit 1; }
.venv/bin/python scripts/common/render_runtime_config.py --role node1 --repo-root "$REPO_ROOT"
mkdir -p data/events data/clips data/keyframes results/node1
chmod 0750 data data/events data/clips data/keyframes results results/node1 2>/dev/null || true

.venv/bin/python scripts/common/validate_policy.py --policy "$POLICY_PATH"
.venv/bin/python scripts/common/apply_migrations.py --db-path "$DB_PATH" --migrations-dir migrations
.venv/bin/python -m pytest -q tests/unit tests/integration

echo "[OK] Node1 Step 1 security and migration setup completed"
