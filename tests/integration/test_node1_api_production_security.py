import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _prepare_tmp_runtime(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "migrations").mkdir()
    source_migrations = Path(__file__).parents[2] / "migrations"
    for source in source_migrations.glob("*.sql"):
        (tmp_path / "migrations" / source.name).write_text(source.read_text())
    for d in ["clips", "keyframes", "datasets"]:
        (tmp_path / "data" / d).mkdir(parents=True, exist_ok=True)
    policy = tmp_path / "policy.yaml"
    policy.write_text(f"""
version: 2
cameras:
  - camera_id: c922_node2_gate
    source_ip: 192.168.29.188
    node2_url: http://192.168.29.188:8082
    allowed_node1_ips: [192.168.29.20]
    allowed_ports: [5000, 5001]
    allowed_profiles: [mjpeg_720p30]
    allowed_devices: [/dev/video0]
media:
  clip_root: {tmp_path / 'data' / 'clips'}
  keyframe_root: {tmp_path / 'data' / 'keyframes'}
  dataset_root: {tmp_path / 'data' / 'datasets'}
node2_control:
  trusted_client_ips: [127.0.0.1]
""", encoding="utf-8")
    monkeypatch.setenv("AI_CAMERA_DB", str(tmp_path / "events.db"))
    monkeypatch.setenv("AI_CAMERA_POLICY", str(policy))
    monkeypatch.setenv("AI_CAMERA_NODE1_API_TOKEN", "secret")
    monkeypatch.delenv("AI_CAMERA_NODE1_API_KEYS", raising=False)
    monkeypatch.delenv("AI_CAMERA_API_CLIENTS", raising=False)
    monkeypatch.delenv("AI_CAMERA_NODE1_ENFORCE_API_CLIENTS", raising=False)


def test_node1_api_token_protects_non_public_routes(tmp_path: Path, monkeypatch):
    _prepare_tmp_runtime(tmp_path, monkeypatch)
    import services.node1_api_gateway.app as module
    module = importlib.reload(module)
    with TestClient(module.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/events").status_code == 403
        assert client.get("/events", headers={"X-API-Key": "secret"}).status_code == 200


def test_node1_security_runtime_reports_posture(tmp_path: Path, monkeypatch):
    _prepare_tmp_runtime(tmp_path, monkeypatch)
    import services.node1_api_gateway.app as module
    module = importlib.reload(module)
    with TestClient(module.app) as client:
        response = client.get("/security/runtime", headers={"X-API-Key": "secret"})
        assert response.status_code == 200
        assert response.json()["node1_api"]["api_keys_configured"] is True
