# Portable Node1/Node2 deployment

The repository may be unpacked under any user account. The recommended location is:

```bash
export AI_CAMERA_REPO_ROOT="$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
```

Generated systemd units and runtime configs are rendered from `deploy/ai-camera.env` and should not contain stale hard-coded paths from another machine.

## 1. Configure Node1

```bash
mkdir -p "$HOME/dev/pub/mig1"
tar -xzf cctv-ip-or-lan-usb-camera-ingest-ai-inference.tar.gz -C "$HOME/dev/pub/mig1"
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Edit `deploy/ai-camera.env`:

```text
AI_CAMERA_NODE_ROLE=node1
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
AI_CAMERA_PROFILE=mjpeg_720p30
AI_CAMERA_CAMERA_ID=c922_node2_gate
AI_CAMERA_NODE1_RTP_PORT=5000
AI_CAMERA_CAPTURE_UDP_PORT=5001
AI_CAMERA_DATASET_ROOT=data/datasets
AI_CAMERA_CAPTURE_MAX_DURATION_SEC=7200
AI_CAMERA_EVENT_LOG=results/node1/events.jsonl
```

Install dependencies and create the Node1 venv:

```bash
scripts/node1/install_node1_dependencies.sh
RECREATE_VENV=1 scripts/node1/setup_node1_venv.sh
source .venv/bin/activate
```

Confirm Node1 OpenCV/GStreamer:

```bash
python - <<'PY'
import cv2
print(cv2.__version__)
for line in cv2.getBuildInformation().splitlines():
    if "GStreamer" in line:
        print(line)
PY
```

Expected: `GStreamer: YES`.

Prepare and install Node1 services:

```bash
set -a; source deploy/ai-camera.env; set +a
export AI_CAMERA_REPO_ROOT="$PWD"
./scripts/common/prepare_deployment.sh node1
sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_CAPTURE_UDP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_TRANSPORT,AI_CAMERA_DATASET_ROOT,AI_CAMERA_CAPTURE_MAX_DURATION_SEC,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG,AI_CAMERA_LATENCY_THRESHOLD_MS,AI_CAMERA_LATENCY_WINDOW_SAMPLES \
  "$PWD/.venv/bin/python" scripts/common/install_systemd_units.py --role node1
sudo systemctl daemon-reload
sudo systemctl enable --now node1-ai-camera-api.service node1-ai-camera-receiver.service
```

Validate Node1:

```bash
curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_API_PORT}/health" | python3 -m json.tool
curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_METRICS_PORT}/metrics" | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total' -A 2
sudo ss -lunp | grep ":${AI_CAMERA_NODE1_RTP_PORT}"
```

## 2. Configure Node2

Sync or unpack the same source tree on Node2. Do not sync `.venv` from Node1.

```bash
cd "$HOME/dev/pub/mig1/cctv-ip-or-lan-usb-camera-ingest-ai-inference"
cp deploy/ai-camera.env.example deploy/ai-camera.env
```

Edit:

```text
AI_CAMERA_NODE_ROLE=node2
AI_CAMERA_NODE1_IP=192.168.29.20
AI_CAMERA_NODE2_IP=192.168.29.188
AI_CAMERA_DEVICE=/dev/video0
AI_CAMERA_PROFILE=mjpeg_720p30
```

Install dependencies and create Node2 venv:

```bash
scripts/node2/install_node2_dependencies.sh
PYTHONNOUSERSITE=1 RECREATE_VENV=1 scripts/node2/setup_node2_venv.sh
source .venv/bin/activate
```

Validate camera mode:

```bash
v4l2-ctl --device=/dev/video0 --list-formats-ext | grep -A8 -B2 '1280x720'
```

Expected under MJPG: `1280x720` with `0.033s (30.000 fps)`.

Prepare and install Node2 service:

```bash
set -a; source deploy/ai-camera.env; set +a
export AI_CAMERA_REPO_ROOT="$PWD"
./scripts/common/prepare_deployment.sh node2
sudo --preserve-env=AI_CAMERA_REPO_ROOT,AI_CAMERA_NODE1_IP,AI_CAMERA_NODE2_IP,AI_CAMERA_NODE1_API_PORT,AI_CAMERA_NODE1_RTP_PORT,AI_CAMERA_CAPTURE_UDP_PORT,AI_CAMERA_NODE1_METRICS_PORT,AI_CAMERA_NODE2_API_PORT,AI_CAMERA_VENV_DIR,AI_CAMERA_POLICY,AI_CAMERA_DB,AI_CAMERA_MIGRATIONS,AI_CAMERA_PROFILE,AI_CAMERA_CAMERA_ID,AI_CAMERA_DEVICE,AI_CAMERA_EVENT_LOG,PYTHONNOUSERSITE \
  "$PWD/.venv/bin/python" scripts/common/install_systemd_units.py --role node2
sudo systemctl daemon-reload
sudo systemctl enable --now node2-camera-control-agent.service
```

Validate Node2 from Node1:

```bash
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/health" | python3 -m json.tool
curl -fsS "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/stream/status" | python3 -m json.tool
```

## 3. Firewall

```bash
sudo ufw allow from "$AI_CAMERA_NODE2_IP" to "$AI_CAMERA_NODE1_IP" port "$AI_CAMERA_NODE1_RTP_PORT" proto udp
sudo ufw allow from "$AI_CAMERA_NODE2_IP" to "$AI_CAMERA_NODE1_IP" port "$AI_CAMERA_CAPTURE_UDP_PORT" proto udp
sudo ufw allow from "$AI_CAMERA_NODE1_IP" to "$AI_CAMERA_NODE2_IP" port "$AI_CAMERA_NODE2_API_PORT" proto tcp
sudo ufw allow from "$AI_CAMERA_NODE1_IP" to "$AI_CAMERA_NODE1_IP" port "$AI_CAMERA_NODE1_METRICS_PORT" proto tcp
sudo ufw allow from "$AI_CAMERA_NODE1_IP" to "$AI_CAMERA_NODE1_IP" port 8080 proto tcp
sudo ufw allow from "$AI_CAMERA_NODE1_IP" to "$AI_CAMERA_NODE1_IP" port 9090 proto tcp
sudo ufw allow from "$AI_CAMERA_NODE1_IP" to "$AI_CAMERA_NODE1_IP" port 3000 proto tcp
```

Adjust Grafana/Prometheus exposure if other LAN machines need dashboard access.

## 4. Production RTP validation

Run from Node1:

```bash
./scripts/validate_step9_streaming.sh
```

Manual equivalent:

```bash
curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/stream/start" \
  -H 'Content-Type: application/json' \
  -d '{"camera_id":"c922_node2_gate","node1_ip":"192.168.29.20","port":5000,"device":"/dev/video0","profile":"mjpeg_720p30","transport":"rtp"}' | python3 -m json.tool

curl -fsS "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/stream/status" | python3 -m json.tool

for i in 1 2 3 4 5; do
  curl -fsS "http://${AI_CAMERA_NODE1_IP}:${AI_CAMERA_NODE1_METRICS_PORT}/metrics" | grep -E 'ai_camera_receiver_fps|ai_camera_frames_total' -A 2
  sleep 1
done

curl -fsS -X POST "http://${AI_CAMERA_NODE2_IP}:${AI_CAMERA_NODE2_API_PORT}/stream/stop" | python3 -m json.tool
```

## 5. Step 10/11/12 validation gates

```bash
# Reproducibility
RUN_PREPARE=1 ./scripts/validate_step10_reproducible_deployment.sh node1
RUN_PREPARE=1 ./scripts/validate_step10_reproducible_deployment.sh node2
RUN_STREAM=1 ./scripts/validate_step10_reproducible_deployment.sh node1

# Receiver-side bounded-slices latency
./scripts/validate_step11_latency_monitoring.sh

# Timestamped E2E latency and YOLO postprocess
./scripts/validate_step12_e2e_latency.sh
./scripts/validate_step12_yolo_onnx.sh
```

## 6. Step 13 Grafana and capture-session demo

Render Prometheus config and start the Node1 stack:

```bash
./scripts/common/render_prometheus_config.sh
docker compose -f docker/docker-compose.node1.yml up -d --force-recreate
docker compose -f docker/docker-compose.node1.yml ps
```

Required compose volume paths because `docker-compose.node1.yml` lives inside `docker/`:

```yaml
../configs/runtime/prometheus.yml:/etc/prometheus/prometheus.yml:ro
./grafana/provisioning:/etc/grafana/provisioning:ro
./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

Health and dashboard checks:

```bash
curl -fsS "http://${AI_CAMERA_NODE1_IP}:9090/-/healthy"
curl -fsS "http://${AI_CAMERA_NODE1_IP}:3000/api/health" | python3 -m json.tool
curl -fsS -u admin:admin "http://${AI_CAMERA_NODE1_IP}:3000/api/search?query=AI%20Camera" | python3 -m json.tool
```

Open:

```text
Grafana dashboard:
http://192.168.29.20:3000/d/ai-camera-capture-session-demo/ai-camera-capture-session-demo

Node1 capture UI:
http://192.168.29.20:8080/ui/capture
```

Run automated validation from Node1:

```bash
./scripts/validate_step13_grafana_stack.sh
./scripts/validate_step13_capture_session.sh
```

Expected capture validation:

```text
status=completed frames>0
[OK] Step 13 capture-session dataset validation completed
```

## 7. Runtime artifacts to keep out of commits

Do not stage these paths:

```text
.venv/
configs/runtime/*.yml
results/
data/events/*.db*
data/datasets/
docker/configs/
docker/docker/
```

Use targeted `git add` for source/config/docs/tests only.
