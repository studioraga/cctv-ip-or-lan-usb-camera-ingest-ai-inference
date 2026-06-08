# Python virtual environment setup for Node1 and Node2

This project should not run against uncontrolled system Python. Use a local `.venv` inside the repository on each machine.

Important: do not copy or sync `.venv` between Node1 and Node2. Node1 is x86_64 and Node2 Jetson is aarch64, so Python native wheels and linked libraries are architecture-specific. Sync the source tree, `requirements-node1.txt`, `requirements-node2.txt`, and scripts. Recreate `.venv` independently on each node.

## Node1

Node1 receives the RTP/JPEG stream, decodes frames through GStreamer/OpenCV, and optionally runs ONNX Runtime inference.

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework
./scripts/node1/setup_node1_venv.sh
source .venv/bin/activate
python -c "import cv2, onnxruntime as ort; print(cv2.__version__); print(ort.get_available_providers())"
```

Run the receiver agent:

```bash
./scripts/node1/run_node1_receiver_agent.sh
```

## Node2

Node2 controls the C922/V4L2/GStreamer sender. The Python environment is intentionally small because streaming is performed by GStreamer.

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework
./scripts/node2/setup_node2_venv.sh
source .venv/bin/activate
python -c "import yaml; print('node2 venv ok')"
```

Run the streamer:

```bash
NODE1_IP=192.168.29.20 PROFILE=mjpeg_720p30 ./scripts/node2/run_node2_streamer_controller.sh --tegrastats
```

## Source sync pattern

From Node1/control machine:

```bash
cd ~/dev/ai-camera-node1-node2-agent-framework
NODE2_USER=srrmk NODE2_IP=192.168.29.188 REMOTE_DIR=~/dev/ai-camera-node1-node2-agent-framework \
  ./scripts/common/sync_repo_to_node2.sh
```

The sync script excludes `.venv`, results, caches, and Python bytecode.
