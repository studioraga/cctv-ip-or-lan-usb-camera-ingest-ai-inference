#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/node1/watch_motion_live_mp4_vlc.sh [--camera-id ID] [--node1-url URL] [--preview]

Polls Node1 until a motion capture session is active, then opens live.mp4 in
VLC. With --preview, the script uses the active session if present; otherwise it
opens the most recent completed capture session preview.mp4. If VLC is not
installed, the script prints the URL so another LAN machine can open it manually.
USAGE
}

CAMERA_ID="${AI_CAMERA_CAMERA_ID:-c922_node2_gate}"
NODE1_URL=""
PREVIEW=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --camera-id) CAMERA_ID="$2"; shift 2 ;;
    --node1-url) NODE1_URL="${2%/}"; shift 2 ;;
    --preview) PREVIEW=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"
export AI_CAMERA_ENV_FILE="${AI_CAMERA_ENV_FILE:-$REPO_ROOT/deploy/ai-camera.env}"
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/lib/runtime_env.sh"
export AI_CAMERA_REPO_ROOT="$REPO_ROOT"

if [[ -z "$NODE1_URL" ]]; then
  NODE1_IP="${AI_CAMERA_NODE1_IP:-127.0.0.1}"
  NODE1_URL="http://${NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}"
fi

session_from_current() {
  local json
  json="$(curl -fsS "${NODE1_URL}/motion/streams/current?camera_id=${CAMERA_ID}" || true)"
  python3 -c 'import json,sys
try:
    data=json.loads(sys.argv[1]) if sys.argv[1] else {}
except Exception:
    data={}
print(data.get("session_id", "") if data.get("active") else "")' "$json"
}

session_from_latest() {
  local json
  json="$(curl -fsS "${NODE1_URL}/capture/sessions?camera_id=${CAMERA_ID}&limit=1" || true)"
  python3 -c 'import json,sys
try:
    data=json.loads(sys.argv[1]) if sys.argv[1] else []
except Exception:
    data=[]
print(data[0].get("session_id", "") if data else "")' "$json"
}

SESSION_ID=""
if [[ "$PREVIEW" -eq 1 ]]; then
  SESSION_ID="$(session_from_current)"
  if [[ -z "$SESSION_ID" ]]; then
    SESSION_ID="$(session_from_latest)"
  fi
  if [[ -z "$SESSION_ID" ]]; then
    echo "No active or previous capture session found for ${CAMERA_ID} at ${NODE1_URL}." >&2
    exit 1
  fi
else
  while true; do
    SESSION_ID="$(session_from_current)"
    if [[ -n "$SESSION_ID" ]]; then
      break
    fi
    echo "No active motion stream yet for ${CAMERA_ID} at ${NODE1_URL}; polling..."
    sleep 1
  done
fi

if [[ "$PREVIEW" -eq 1 ]]; then
  URL="${NODE1_URL}/motion/streams/${SESSION_ID}/preview.mp4"
else
  URL="${NODE1_URL}/motion/streams/${SESSION_ID}/live.mp4"
fi

echo "SESSION_ID=${SESSION_ID}"
echo "URL=${URL}"
if command -v vlc >/dev/null 2>&1; then
  exec vlc "$URL"
else
  echo "VLC not found. Open the URL above from any LAN machine."
fi
