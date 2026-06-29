#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Step 16 production-readiness validation ==="
echo "repo=$REPO_ROOT"

echo "=== Python compile ==="
python3 -m compileall -q agents services scripts tests

echo "=== Focused production-readiness tests ==="
pytest -q \
  tests/unit/test_api_security.py \
  tests/unit/test_request_signing.py \
  tests/unit/test_model_registry.py \
  tests/unit/test_storage_retention.py \
  tests/unit/test_event_indexer.py \
  tests/integration/test_node1_api_production_security.py

echo "=== Full unit/integration suite ==="
pytest -q

echo "=== ONNX provider inventory (non-fatal when onnxruntime is absent) ==="
python3 scripts/models/validate_onnx_provider.py --provider "${AI_CAMERA_ONNX_EXECUTION_PROVIDER:-auto}" || true

echo "=== Docker Compose config validation (if docker compose is installed) ==="
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-validation-only-change-me}" \
  AI_CAMERA_OBSERVABILITY_BIND="${AI_CAMERA_OBSERVABILITY_BIND:-127.0.0.1}" \
  docker compose -f docker/docker-compose.node1.yml config >/tmp/ai_camera_step16_compose.yml
  echo "[OK] docker compose config rendered"
else
  echo "[SKIP] docker compose not available"
fi

echo "=== Source hygiene check ==="
find . -path './.git' -prune -o -type d -name '__pycache__' -print0 | xargs -0r rm -rf
find . -path './.git' -prune -o -name '*.pyc' -print0 | xargs -0r rm -f
if find . -path './.git' -prune -o \( -name '*.pyc' -o -name '__pycache__' \) -print | grep -q .; then
  echo "[FAIL] Python bytecode/cache files exist"
  exit 1
else
  echo "[OK] no Python bytecode/cache files found"
fi

echo "PASS: Step 16 production-readiness baseline"
