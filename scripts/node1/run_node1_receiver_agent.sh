#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
source .venv/bin/activate
mkdir -p results/node1
python agents/node1/node1_receiver_agent.py \
  --port "${PORT:-5000}" \
  --event-log "${EVENT_LOG:-results/node1/events.jsonl}" "$@"
