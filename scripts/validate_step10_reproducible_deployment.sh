#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ROLE="${1:-${AI_CAMERA_NODE_ROLE:-all}}"
RUN_PREPARE="${RUN_PREPARE:-1}"
RUN_STREAM="${RUN_STREAM:-0}"
SOURCE_HYGIENE="${SOURCE_HYGIENE:-0}"
OUT_DIR="${OUT_DIR:-results/step10}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/validate_step10_${ROLE}_$(date +%Y%m%d_%H%M%S).txt"

log(){ echo "$*" | tee -a "$OUT"; }
run(){ log "+ $*"; "$@" 2>&1 | tee -a "$OUT"; }
section(){ log ""; log "=== $* ==="; }

section "Step 10 reproducible deployment validation"
log "repo=$REPO_ROOT"
log "role=$ROLE RUN_PREPARE=$RUN_PREPARE RUN_STREAM=$RUN_STREAM SOURCE_HYGIENE=$SOURCE_HYGIENE"

section "Load environment"
if [ -f deploy/ai-camera.env ]; then
  # shellcheck disable=SC1091
  set -a; source deploy/ai-camera.env; set +a
  log "loaded deploy/ai-camera.env"
else
  log "[WARN] deploy/ai-camera.env not found; using process environment only"
fi
export AI_CAMERA_REPO_ROOT="${AI_CAMERA_REPO_ROOT:-$REPO_ROOT}"

section "Source hygiene checks"
if [ "$SOURCE_HYGIENE" = "1" ]; then
  bad=""
  while IFS= read -r p; do bad+="$p
"; done < <(find . \
    -path './.git' -prune -o \
    \( -path './.venv' -o -path './.venv.backup-*' -o -name '__pycache__' -o -name '*.pyc' -o \
       -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db-wal' -o -name '*.db-shm' -o \
       -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' \) -print)
  if [ -n "$bad" ]; then
    log "[FAIL] source hygiene found runtime artifacts:"
    printf '%s' "$bad" | tee -a "$OUT"
    exit 1
  fi
  log "[OK] no obvious runtime artifacts in source tree"
else
  log "skipped source hygiene; set SOURCE_HYGIENE=1 for clean archive/source validation"
fi

section "Static validation"
run ./scripts/ci/validate_static.sh

section "Environment detection"
run python3 scripts/common/detect_environment.py --json

section "Role-specific runtime validation"
case "$ROLE" in
  node1)
    run ./scripts/ci/validate_node1_runtime.sh
    ;;
  node2)
    run ./scripts/ci/validate_node2_runtime.sh
    ;;
  all)
    log "role=all: running static + environment only here; run this script on each node with node1/node2 for runtime checks"
    ;;
  *)
    log "[FAIL] unsupported role: $ROLE; use node1, node2, or all"
    exit 2
    ;;
esac

section "Prepare deployment"
if [ "$RUN_PREPARE" = "1" ] && [ "$ROLE" != "all" ]; then
  run ./scripts/common/prepare_deployment.sh "$ROLE"
else
  log "skipped prepare_deployment"
fi

section "Systemd and health checks"
if [ "$ROLE" = "node1" ]; then
  systemctl is-active node1-ai-camera-api.service 2>/dev/null | tee -a "$OUT" || true
  systemctl is-active node1-ai-camera-receiver.service 2>/dev/null | tee -a "$OUT" || true
  if [ -n "${AI_CAMERA_NODE1_IP:-}" ]; then
    curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT:-8080}/health" | tee -a "$OUT" || log "[WARN] Node1 API health failed"
    curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_METRICS_PORT:-9101}/metrics" | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total|ai_camera_decode_failures_total|ai_camera_latency_bounded_slice_count|ai_camera_latency_window_variation_ms' -A 2 | tee -a "$OUT" || log "[WARN] Node1 receiver metrics failed"
  fi
elif [ "$ROLE" = "node2" ]; then
  systemctl is-active node2-camera-control-agent.service 2>/dev/null | tee -a "$OUT" || true
  if [ -n "${AI_CAMERA_NODE2_IP:-}" ]; then
    curl -fsS "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT:-8082}/health" | tee -a "$OUT" || log "[WARN] Node2 health failed"
  fi
fi

section "Optional Step 9 streaming validation"
if [ "$RUN_STREAM" = "1" ]; then
  if [ "$ROLE" != "node1" ]; then
    log "[FAIL] RUN_STREAM=1 must be launched from Node1 because Node1 is the authorized control client"
    exit 3
  fi
  run ./scripts/validate_step9_streaming.sh
else
  log "skipped streaming; set RUN_STREAM=1 on Node1 to run API-controlled streaming test"
fi

section "Result"
log "[OK] Step 10 reproducible deployment validation completed"
log "output=$OUT"
