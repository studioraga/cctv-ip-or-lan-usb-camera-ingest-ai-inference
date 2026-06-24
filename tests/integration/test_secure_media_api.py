import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def test_clip_endpoint_uses_clip_id_and_rejects_old_path_endpoint(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "migrations").mkdir()
    source_migrations = Path(__file__).parents[2] / "migrations"
    for source in source_migrations.glob("*.sql"):
        (tmp_path / "migrations" / source.name).write_text(source.read_text())

    clips = tmp_path / "data" / "clips"
    keyframes = tmp_path / "data" / "keyframes"
    clips.mkdir(parents=True)
    keyframes.mkdir(parents=True)
    clip = clips / "clip1.mp4"
    clip.write_bytes(b"video")
    keyframe = keyframes / "evt1.jpg"
    keyframe.write_bytes(b"jpeg")

    policy = tmp_path / "policy.yaml"
    policy.write_text(f"""
version: 2
cameras:
  - camera_id: c922_node2_gate
    source_ip: 192.168.29.188
    node2_url: http://192.168.29.188:8082
    allowed_node1_ips: [192.168.29.20]
    allowed_ports: [5000]
    allowed_profiles: [mjpeg_720p30]
    allowed_devices: [/dev/video0]
media:
  clip_root: {clips}
  keyframe_root: {keyframes}
node2_control:
  trusted_client_ips: [127.0.0.1]
""", encoding="utf-8")

    monkeypatch.setenv("AI_CAMERA_DB", str(tmp_path / "events.db"))
    monkeypatch.setenv("AI_CAMERA_POLICY", str(policy))
    monkeypatch.setenv("AI_CAMERA_ID", "c922_node2_gate")

    import services.node1_api_gateway.app as module
    module = importlib.reload(module)
    module.db.upsert_camera("c922_node2_gate", "cam", "usb", "192.168.29.188")
    module.db.insert_clip({
        "clip_id": "clip1", "camera_id": "c922_node2_gate",
        "start_ts": "2026-01-01T00:00:00+00:00",
        "end_ts": "2026-01-01T00:00:02+00:00",
        "path": str(clip), "keyframe_path": str(keyframe), "duration_sec": 2,
    })
    module.db.insert_event({
        "event_id": "evt1", "camera_id": "c922_node2_gate", "clip_id": "clip1",
        "ts": "2026-01-01T00:00:01+00:00", "event_type": "motion_detected",
    })

    with TestClient(module.app) as client:
        response = client.get("/clips/clip1/file")
        assert response.status_code == 200
        assert response.content == b"video"
        assert client.get("/clips/file", params={"path": "/etc/passwd"}).status_code == 404
        assert client.get("/events/evt1/keyframe").status_code == 200


def test_motion_stream_mp4_endpoint_serves_dataset_artifact(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "migrations").mkdir()
    source_migrations = Path(__file__).parents[2] / "migrations"
    for source in source_migrations.glob("*.sql"):
        (tmp_path / "migrations" / source.name).write_text(source.read_text())

    clips = tmp_path / "data" / "clips"
    keyframes = tmp_path / "data" / "keyframes"
    datasets = tmp_path / "data" / "datasets"
    live_dir = datasets / "cap_motion" / "artifacts"
    live_dir.mkdir(parents=True)
    live_mp4 = live_dir / "live.mp4"
    live_mp4.write_bytes(b"fragmented-mp4")
    (datasets / "cap_motion" / "manifest.json").write_text("{}")
    clips.mkdir(parents=True, exist_ok=True)
    keyframes.mkdir(parents=True, exist_ok=True)

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
  clip_root: {clips}
  keyframe_root: {keyframes}
  dataset_root: {datasets}
node2_control:
  trusted_client_ips: [127.0.0.1]
""", encoding="utf-8")

    monkeypatch.setenv("AI_CAMERA_DB", str(tmp_path / "events.db"))
    monkeypatch.setenv("AI_CAMERA_POLICY", str(policy))
    monkeypatch.setenv("AI_CAMERA_ID", "c922_node2_gate")

    import services.node1_api_gateway.app as module
    module = importlib.reload(module)
    module.db.upsert_camera("c922_node2_gate", "cam", "usb", "192.168.29.188")
    module.db.create_capture_session({
        "session_id": "cap_motion",
        "camera_id": "c922_node2_gate",
        "profile": "mjpeg_720p30",
        "transport": "timed_jpeg_udp",
        "device": "/dev/video0",
        "node1_ip": "192.168.29.20",
        "node2_ip": "192.168.29.188",
        "udp_port": 5001,
        "duration_sec": 60,
        "status": "completed",
        "dataset_path": str(datasets / "cap_motion"),
    })

    with TestClient(module.app) as client:
        response = client.get("/motion/streams/cap_motion/live.mp4")
        assert response.status_code == 200
        assert response.content == b"fragmented-mp4"
        current = client.get("/motion/streams/current?camera_id=c922_node2_gate")
        assert current.status_code == 200
        assert current.json()["active"] is False
