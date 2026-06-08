# Architecture Notes

## Data plane

Node2 streams C922 MJPEG frames over RTP/UDP to Node1. Node1 depayloads and decodes the stream into BGR frames for OpenCV and optional ONNX Runtime inference.

## Control plane

The initial agent framework separates data-plane streaming from control decisions. Node1 is the policy and orchestration point. Node2 is the camera execution point.

Future control APIs can be implemented over REST/gRPC with mTLS.

## Observability plane

Node1 emits JSONL event logs. Node2 uses tegrastats for thermal/power/CPU monitoring.

## Security plane

The default LAN rule is to allow only Node2 `192.168.29.188` to send UDP/5000 traffic to Node1 `192.168.29.20`.
