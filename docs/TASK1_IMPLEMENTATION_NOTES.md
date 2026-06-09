# Task1 Implementation Notes

This repository extends the working Node1/Node2 camera transport into a local-first AI CCTV service layer.

Implemented in this task package:

1. `mjpeg_480p30` receiver profile added to `agents/node1/node1_receiver_agent.py`.
2. Node2 FastAPI control agent added under `services/node2_control_agent/`.
3. Node1 FastAPI API gateway added under `services/node1_api_gateway/`.
4. Prometheus metrics added to Node1 receiver and Node2 control service.
5. SQLite event schema added through `services/common/event_db.py`.
6. ONNX object detection scaffold added under `services/node1_inference_worker/`.
7. Event-triggered keyframe and simple clip capture added through receiver `--motion-events`.
8. Deterministic natural-language query endpoint added at Node1 `/query`.
9. Qdrant adapter scaffold added under `services/node1_event_indexer/qdrant_store.py`.
10. Policy, mTLS scripts, systemd services, and Docker/Prometheus artifacts added.

The goal of this implementation is to keep the tested RTP camera path intact while adding independently testable service-layer building blocks.
