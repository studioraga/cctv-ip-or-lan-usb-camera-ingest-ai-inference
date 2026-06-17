# Step 1 changed and added files

- Only in .: .pytest_cache
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/README.md and ./README.md differ
- Only in .: STEP1_CHANGE_MANIFEST.md
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/agents/common/__pycache__/telemetry.cpython-313.pyc and ./agents/common/__pycache__/telemetry.cpython-313.pyc differ
- Only in ./agents/node1: __pycache__
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/agents/node1/node1_receiver_agent.py and ./agents/node1/node1_receiver_agent.py differ
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/agents/node2/__pycache__/node2_streamer_controller.cpython-313.pyc and ./agents/node2/__pycache__/node2_streamer_controller.cpython-313.pyc differ
- Only in ./configs: security
- Only in ./docs: STEP1_MIGRATIONS_POLICY_MEDIA_SECURITY.md
- Only in .: migrations
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/policies/security_policy.yaml and ./policies/security_policy.yaml differ
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/requirements-node1.txt and ./requirements-node1.txt differ
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/requirements-node2.txt and ./requirements-node2.txt differ
- Only in ./scripts/common: __pycache__
- Only in ./scripts/common: apply_migrations.py
- Only in ./scripts/common: validate_policy.py
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/scripts/node1/init_event_db.sh and ./scripts/node1/init_event_db.sh differ
- Only in ./scripts/node1: setup_step1_security.sh
- Only in ./scripts/node2: setup_step1_security.sh
- Only in ./services/__pycache__: __init__.cpython-313.pyc
- Only in ./services/common/__pycache__: __init__.cpython-313.pyc
- Only in ./services/common/__pycache__: event_db.cpython-313.pyc
- Only in ./services/common/__pycache__: migrations.cpython-313.pyc
- Only in ./services/common/__pycache__: path_security.cpython-313.pyc
- Only in ./services/common/__pycache__: policy.cpython-313.pyc
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/services/common/event_db.py and ./services/common/event_db.py differ
- Only in ./services/common: migrations.py
- Only in ./services/common: path_security.py
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/services/common/policy.py and ./services/common/policy.py differ
- Only in ./services/node1_api_gateway/__pycache__: __init__.cpython-313.pyc
- Only in ./services/node1_api_gateway/__pycache__: app.cpython-313.pyc
- Only in ./services/node1_api_gateway/__pycache__: schemas.cpython-313.pyc
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/services/node1_api_gateway/app.py and ./services/node1_api_gateway/app.py differ
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/services/node1_api_gateway/schemas.py and ./services/node1_api_gateway/schemas.py differ
- Only in ./services/node1_event_indexer/__pycache__: __init__.cpython-313.pyc
- Only in ./services/node1_event_indexer/__pycache__: indexer.cpython-313.pyc
- Only in ./services/node1_event_indexer/__pycache__: qdrant_store.cpython-313.pyc
- Only in ./services/node1_inference_worker: __pycache__
- Only in ./services/node1_inference_worker/detectors: __pycache__
- Only in ./services/node1_query_engine/__pycache__: __init__.cpython-313.pyc
- Only in ./services/node1_query_engine/__pycache__: nl_parser.cpython-313.pyc
- Only in ./services/node2_control_agent: __pycache__
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/services/node2_control_agent/app.py and ./services/node2_control_agent/app.py differ
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/systemd/node1-ai-camera-api.service and ./systemd/node1-ai-camera-api.service differ
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/systemd/node1-ai-camera-receiver.service and ./systemd/node1-ai-camera-receiver.service differ
- Files /mnt/data/original_step1_compare/cctv-ip-or-lan-usb-camera-ingest-ai-inference/systemd/node2-camera-control-agent.service and ./systemd/node2-camera-control-agent.service differ
- Only in .: tests

---

## Later Step 13 note

The Step 1 migration and policy framework now also supports Step 13 capture
sessions through `migrations/003_capture_sessions.sql`, dataset artifact access,
and policy allow-listing of the dedicated capture UDP port `5001`.
