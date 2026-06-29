# Step 16 — Production-readiness system design baseline

Step 16 packages the Step 15 Node2 YOLO motion-trigger milestone into a production-readiness slice.  It does **not** claim the product is fully customer-ready; it implements the next bounded layer needed before customer-premises pilots.

## 1. Gap-to-implementation map

| Gap | Step 16 implementation |
|---|---|
| 1. Node1 API authentication/authorization | `services/common/api_security.py` plus Node1 middleware, API key/RBAC roles, client CIDR allow-list, `/security/runtime`, auth-denied metric. |
| 2. mTLS or signed local API calls | `services/common/request_signing.py`; Node2 watcher signs Node1 webhooks; Node1 signs Node2 control calls; Node2 can require signed control requests. This is the in-app signed-call baseline before full mTLS termination. |
| 3. Grafana/Prometheus hardening | Docker Compose no longer defaults to host network + anonymous Grafana. Observability binds to `127.0.0.1` by default; Grafana admin password is required; anonymous access defaults off. |
| 4. Model registry metadata | `services/common/model_registry.py`, `/models/registry`, `/models/verify`, model ID/version/path/SHA-256/provider/thresholds. Node2 trigger payloads include `model_metadata`. |
| 5. ONNX provider validation | `services/common/onnx_provider_validation.py`, `scripts/models/validate_onnx_provider.py`, detector provider selection for `auto`, `cpu`, `cuda`, `tensorrt`. |
| 6. Trigger-to-capture-start latency | Node1 observes `ai_camera_trigger_to_capture_start_latency_ms` from Node2 `trigger_wall_ns` to capture-session acceptance. Live MP4 readiness latency is also exported. |
| 7. Storage retention/quota | `services/common/storage_retention.py`, `/storage/status`, `/storage/prune`, env-driven max bytes/min free/retention days/prune batch. |
| 8. Multi-camera abstraction | policy exposes `policy.cameras()`, Node1 `/cameras/runtime`, runtime config supports `AI_CAMERA_ADDITIONAL_CAMERAS`. |
| 9. Qdrant/indexer scaffold to real pipeline | `services/node1_event_indexer/indexer.py` builds deterministic local evidence embeddings into JSONL and optionally upserts to Qdrant. |
| 10. FastAPI lifespan | Node1 API uses FastAPI lifespan startup instead of deprecated `@app.on_event("startup")`. |

## 2. Security model

```text
External/local client
  -> Node1 FastAPI middleware
      -> public endpoint allow-list (/health, /metrics)
      -> optional IP/CIDR client allow-list
      -> optional API key validation
      -> route role check: viewer / operator / admin / node2
      -> optional signed Node2 webhook verification
  -> route handler
  -> policy validation
  -> DB/artifact access
```

Runtime controls:

```bash
AI_CAMERA_NODE1_API_TOKEN=
AI_CAMERA_NODE1_API_KEYS='viewer:<token>:viewer,operator:<token>:operator|viewer,node2:<token>:node2'
AI_CAMERA_API_CLIENTS='192.168.29.20/32,192.168.29.188/32,127.0.0.1/32'
AI_CAMERA_NODE1_ENFORCE_API_CLIENTS=1
AI_CAMERA_NODE1_PUBLIC_ENDPOINTS=/health,/metrics
```

Signed local calls:

```text
canonical = METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + NONCE + "\n" + SHA256(BODY)
signature = HMAC-SHA256(secret, canonical)
```

Headers:

```text
X-AI-Camera-Timestamp
X-AI-Camera-Nonce
X-AI-Camera-Body-SHA256
X-AI-Camera-Signature
```

This addresses the immediate local-authority gap.  For a strict customer deployment, put Node1 and Node2 behind TLS/mTLS termination using the existing local CA material or a customer-provided PKI, then keep the signed headers as defense-in-depth.

## 3. Orchestration model

```text
Node2 watcher owns /dev/video0 while idle
  -> frame-difference motion gate
  -> YOLO ONNX confirmation
  -> signed POST /motion/events/node2 to Node1
  -> release /dev/video0

Node1 receives signed trigger
  -> validates API/RBAC/source policy
  -> creates capture session
  -> signs Node2 /stream/start request
  -> receives timed_jpeg_udp frames
  -> writes source JPEG dataset + manifest/report/metrics
  -> creates live.mp4 and preview.mp4
  -> exports progress and artifact completeness
  -> signs Node2 /stream/stop request

Node2 watcher waits for terminal session state
  -> cooldown
  -> reopens /dev/video0
```

Step 16 keeps the Step 15 Option A single-owner camera design.  The next orchestration upgrade should be a tee-based continuous pipeline when camera-release/reopen latency becomes a business issue.

## 4. Inference model

```text
motion gate
  -> cheap frame-difference score
  -> only run YOLO when motion crosses threshold

YOLO confirmation
  -> ONNX Runtime provider selection: auto / cpu / cuda / tensorrt
  -> class allow-list
  -> confidence threshold
  -> IoU threshold
  -> detection evidence payload

model provenance
  -> model_id
  -> model version
  -> model path/source URL
  -> SHA-256 configured/verified status
  -> provider intent
  -> thresholds attached to trigger evidence
```

The LLM/RAG layer still should not consume raw frames by default.  It should consume structured facts:

```text
camera_id, event_type, timestamp, detected_classes, confidence, motion_score,
session_id, artifact URLs, manifest path, latency metrics, clip/live_mp4/preview references
```

## 5. Observability model

New or expanded metrics:

```text
ai_camera_api_auth_denied_total
ai_camera_motion_triggers_total{camera_id,label}
ai_camera_motion_score_bucket
ai_camera_motion_top_detection_confidence{camera_id,label}
ai_camera_trigger_to_capture_start_latency_ms_bucket
ai_camera_live_mp4_ready_latency_ms_bucket
ai_camera_capture_session_artifact_complete{camera_id,session_id}
```

The Grafana dashboard now includes sections for:

```text
- motion triggers by class
- top detection confidence
- motion score distribution
- trigger-to-capture-start latency
- live MP4 readiness latency
- dropped/skipped frames
- per-session artifact completeness
```

## 6. Customer deployment model

Recommended profiles:

```text
lab
  - no API token required
  - observability bind can be LAN
  - model checksum optional

demo
  - API token enabled
  - client allow-list enabled
  - signed Node1/Node2 calls enabled
  - Grafana password required
  - checksum warning visible

customer
  - API key/RBAC required
  - signed calls required; TLS/mTLS through reverse proxy preferred
  - Grafana anonymous off
  - Prometheus/Grafana/Qdrant bound to localhost or management VLAN
  - model SHA-256 required
  - storage quota/retention enabled
  - backup/restore and upgrade/rollback documented
```

## 7. Autonomous validation model

Normal CI:

```text
python compileall
pytest unit/integration
request-signing tests
API security/RBAC tests
model registry/checksum tests
storage retention tests
evidence indexer tests
ONNX provider inventory
Docker Compose config render if Docker is installed
```

Hardware-in-loop lab CI:

```text
Step 12 E2E latency
Step 13 capture session
Step 14 live MP4
Step 15 Node2 synthetic + real watcher trigger
Step 16 auth/signing/provider/storage validation
```

Release gate:

```text
no runtime artifacts committed
model checksum configured for customer profile
Grafana admin password set
API token/keys set
signed calls enabled or mTLS configured
storage retention/quota configured
docs updated
startup scripts validated
```

Run:

```bash
./scripts/validate_step16_production_readiness.sh
```
