#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
ai_camera_require_repo
ROLE="${1:-${AI_CAMERA_NODE_ROLE:-}}"
[[ "$ROLE" == node1 || "$ROLE" == node2 ]] || { echo "Usage: $0 node1|node2" >&2; exit 2; }
ENV_FILE="$REPO_ROOT/deploy/ai-camera.env"
if [[ ! -f "$ENV_FILE" ]]; then cp "$REPO_ROOT/deploy/ai-camera.env.example" "$ENV_FILE"; echo "Created $ENV_FILE"; fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
LOCAL_IP="$(ai_camera_primary_ipv4)"
if [[ "$ROLE" == node1 && -z "${AI_CAMERA_NODE1_IP:-}" ]]; then export AI_CAMERA_NODE1_IP="$LOCAL_IP"; fi
if [[ "$ROLE" == node2 && -z "${AI_CAMERA_NODE2_IP:-}" ]]; then export AI_CAMERA_NODE2_IP="$LOCAL_IP"; fi
PY="$(ai_camera_python)"
[[ -x "$PY" ]] || { echo "ERROR: virtual environment missing: $PY" >&2; exit 1; }
"$PY" scripts/common/detect_environment.py --json
"$PY" scripts/common/render_runtime_config.py --role "$ROLE" --repo-root "$REPO_ROOT"
"$PY" scripts/common/validate_policy.py --policy "$(ai_camera_abs_path "$AI_CAMERA_POLICY")"
if [[ "$ROLE" == node1 ]]; then "$PY" scripts/common/apply_migrations.py --db-path "$(ai_camera_abs_path "$AI_CAMERA_DB")" --migrations-dir "$(ai_camera_abs_path "$AI_CAMERA_MIGRATIONS")"; fi
"$PY" -m pytest -q tests/unit tests/integration
cat <<EOF
[OK] Deployment prepared for $ROLE.
Next: sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG "$PY" scripts/common/install_systemd_units.py --role $ROLE
Then: sudo systemctl daemon-reload
EOF
