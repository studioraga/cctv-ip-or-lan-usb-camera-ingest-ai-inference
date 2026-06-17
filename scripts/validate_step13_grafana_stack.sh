#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source scripts/lib/runtime_env.sh
OUT_DIR="results/step13"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/validate_step13_grafana_stack_$(date +%Y%m%d_%H%M%S).txt"
log(){ echo "$*" | tee -a "$OUT"; }

log "=== Step 13 Grafana/Prometheus stack validation ==="
./scripts/common/render_prometheus_config.sh | tee -a "$OUT"
python3 - <<'PY' | tee -a "$OUT"
import json, yaml
from pathlib import Path
for path in ['configs/runtime/prometheus.yml','docker/grafana/provisioning/datasources/prometheus.yml','docker/grafana/provisioning/dashboards/ai-camera.yml']:
    with open(path, 'r', encoding='utf-8') as f:
        yaml.safe_load(f)
    print('YAML OK:', path)
with open('docker/grafana/dashboards/ai-camera-capture-session.json', 'r', encoding='utf-8') as f:
    data=json.load(f)
assert data['uid'] == 'ai-camera-capture-session-demo'
print('Grafana dashboard JSON OK')
PY
if command -v docker >/dev/null 2>&1; then
  docker compose -f docker/docker-compose.node1.yml config >/dev/null
  log "docker compose config OK"
else
  log "docker not installed; skipped compose config"
fi
log "[OK] Step 13 Grafana stack validation completed"
log "output=${OUT}"
