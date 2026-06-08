#!/usr/bin/env bash
set -euo pipefail

NODE2_USER="${NODE2_USER:-srrmk}"
NODE2_IP="${NODE2_IP:-192.168.29.188}"
REMOTE_DIR="${REMOTE_DIR:-~/dev/ai-camera-node1-node2-agent-framework}"

rsync -avh --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'results/' \
  ./ "${NODE2_USER}@${NODE2_IP}:${REMOTE_DIR}/"
