#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"

: "${AI_CAMERA_NODE1_IP:?AI_CAMERA_NODE1_IP is required; set deploy/ai-camera.env}"
: "${AI_CAMERA_NODE2_IP:?AI_CAMERA_NODE2_IP is required; set deploy/ai-camera.env}"
: "${AI_CAMERA_NODE1_API_PORT:?}"
: "${AI_CAMERA_NODE1_METRICS_PORT:?}"
: "${AI_CAMERA_NODE2_API_PORT:?}"

TEMPLATE="$REPO_ROOT/docker/prometheus.yml"
OUT_DIR="$REPO_ROOT/configs/runtime"
OUT_FILE="$OUT_DIR/prometheus.yml"

mkdir -p "$OUT_DIR"

# A failed first Docker bind mount can create configs/runtime/prometheus.yml as a
# directory. Repair that exact generated path so the next compose up can mount it
# as a file.
if [[ -d "$OUT_FILE" ]]; then
  echo "[WARN] $OUT_FILE is a directory; removing stale Docker-created path."
  rm -rf "$OUT_FILE"
fi

if [[ ! -f "$TEMPLATE" ]]; then
  echo "[FAIL] missing Prometheus template: $TEMPLATE" >&2
  exit 1
fi

if command -v envsubst >/dev/null 2>&1; then
  envsubst < "$TEMPLATE" > "$OUT_FILE.tmp"
else
  python3 - <<'PY' "$TEMPLATE" "$OUT_FILE.tmp"
import os, re, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, 'r', encoding='utf-8').read()
text = re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', lambda m: os.environ.get(m.group(1), m.group(0)), text)
open(dst, 'w', encoding='utf-8').write(text)
PY
fi
mv "$OUT_FILE.tmp" "$OUT_FILE"
chmod 0644 "$OUT_FILE"

if [[ ! -f "$OUT_FILE" ]]; then
  echo "[FAIL] generated path is not a file: $OUT_FILE" >&2
  exit 1
fi

if grep -q '\${AI_CAMERA_' "$OUT_FILE"; then
  echo "[FAIL] unresolved AI_CAMERA placeholders remain in $OUT_FILE" >&2
  cat "$OUT_FILE" >&2
  exit 1
fi

echo "[OK] generated configs/runtime/prometheus.yml"
echo "[OK] targets: node1_api=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT} node1_receiver=${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_METRICS_PORT} node2_control=${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}"
