#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[CI] Python compile checks"
python3 -m py_compile \
  agents/node1/node1_receiver_agent.py \
  agents/node2/node2_streamer_controller.py \
  services/common/bounded_slices.py \
  services/common/event_db.py \
  services/common/policy.py \
  services/node1_api_gateway/app.py \
  services/node1_api_gateway/schemas.py \
  services/node1_query_engine/nl_parser.py \
  services/node1_event_indexer/qdrant_store.py \
  services/node1_inference_worker/worker.py \
  services/node1_inference_worker/detectors/motion.py \
  services/node1_inference_worker/detectors/yolo_onnx.py \
  services/node2_control_agent/app.py \
  services/node2_control_agent/streamer_service.py \
  tools/parse_tegrastats.py

echo "[CI] YAML syntax checks"
python3 - <<'PY'
import os
from pathlib import Path
import yaml
for path in list(Path('configs').glob('*.yaml')) + list(Path('policies').glob('*.yaml')):
    with path.open('r', encoding='utf-8') as f:
        yaml.safe_load(f)
    print('YAML OK:', path)
PY

echo "[CI] Shell script syntax checks"
find scripts security -type f -name '*.sh' -print0 | while IFS= read -r -d '' script; do
  bash -n "$script"
  echo "shell OK: $script"
done

echo "[CI] Node2 command generation checks"
python3 - <<'PY'
import os
from agents.node2.node2_streamer_controller import build_gstreamer_command
profiles = ['mjpeg_480p30','mjpeg_720p30','mjpeg_720p60','mjpeg_1080p30','yuyv_640x480']
for p in profiles:
    cmd = build_gstreamer_command(p, os.getenv('AI_CAMERA_TEST_NODE1_IP', '192.0.2.21'), 5000, '/dev/video0')
    line = ' '.join(cmd)
    assert 'gst-launch-1.0' in line
    assert 'udpsink' in line
    if p == 'yuyv_640x480':
        assert 'videoconvert' in line and 'format=UYVY' in line and 'rtpvrawpay' in line
    else:
        assert 'rtpjpegpay' in line
    print('profile OK:', p)
PY

echo "[CI] Query parser smoke"
python3 - <<'PY'
from services.node1_query_engine.nl_parser import parse_question
assert parse_question('summarize activity near the gate').summarize is True
assert parse_question('summarize activity near the gate').event_type == 'motion_detected'
assert parse_question('who came near the gate').event_type == 'person_detected'
assert parse_question('red shirt person').attributes.get('shirt_color') == 'red'
print('query parser OK')
PY

echo "[CI] Static validation PASS"
