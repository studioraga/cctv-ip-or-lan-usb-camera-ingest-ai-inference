from __future__ import annotations

import shutil
from pathlib import Path

from services.common.event_db import EventDB
from services.common.policy import SecurityPolicy
from services.node1_capture_orchestrator.session_manager import CaptureSessionManager


def _copy_migrations(tmp_path: Path) -> Path:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for source in (Path(__file__).parents[2] / "migrations").glob("*.sql"):
        shutil.copy2(source, migrations / source.name)
    return migrations


def _write_policy(path: Path, dataset_root: Path) -> None:
    path.write_text(
        f"""
version: 2
cameras:
  - camera_id: c922_node2_gate
    source_ip: 192.168.29.188
    node2_url: http://192.168.29.188:8082
    allowed_node1_ips: [192.168.29.20]
    allowed_ports: [5001]
    allowed_profiles: [mjpeg_720p30]
    allowed_devices: [/dev/video0]
media:
  clip_root: {dataset_root.parent / 'clips'}
  keyframe_root: {dataset_root.parent / 'keyframes'}
  dataset_root: {dataset_root}
node2_control:
  trusted_client_ips: [127.0.0.1]
""".strip(),
        encoding="utf-8",
    )


def test_mark_stale_capture_sessions_marks_pending_and_running_failed(tmp_path: Path):
    migrations = _copy_migrations(tmp_path)
    db = EventDB(str(tmp_path / "events.db"), str(migrations))
    db.upsert_camera("c922_node2_gate", "cam", "usb", "192.168.29.188")
    for sid, status in [("pending_session", "pending"), ("running_session", "running")]:
        db.create_capture_session({
            "session_id": sid,
            "camera_id": "c922_node2_gate",
            "profile": "mjpeg_720p30",
            "transport": "timed_jpeg_udp",
            "device": "/dev/video0",
            "node1_ip": "192.168.29.20",
            "node2_ip": "192.168.29.188",
            "udp_port": 5001,
            "duration_sec": 20,
            "status": status,
            "dataset_path": str(tmp_path / sid),
        })

    recovered = db.mark_stale_capture_sessions(reason="test recovery")
    assert {row["session_id"] for row in recovered} == {"pending_session", "running_session"}
    for sid in ["pending_session", "running_session"]:
        row = db.get_capture_session(sid)
        assert row is not None
        assert row["status"] == "failed"
        assert row["error"] == "test recovery"
        assert row["ended_at"]
    assert db.get_active_capture_session("c922_node2_gate") is None


def test_capture_session_manager_recovers_stale_sessions_on_startup(tmp_path: Path, monkeypatch):
    migrations = _copy_migrations(tmp_path)
    dataset_root = tmp_path / "datasets"
    policy_path = tmp_path / "policy.yaml"
    _write_policy(policy_path, dataset_root)

    monkeypatch.setenv("AI_CAMERA_NODE1_IP", "192.168.29.20")
    monkeypatch.setenv("AI_CAMERA_NODE2_IP", "192.168.29.188")
    monkeypatch.setenv("AI_CAMERA_CAPTURE_UDP_PORT", "5001")
    monkeypatch.setenv("AI_CAMERA_DATASET_ROOT", str(dataset_root))

    db = EventDB(str(tmp_path / "events.db"), str(migrations))
    db.upsert_camera("c922_node2_gate", "cam", "usb", "192.168.29.188")
    db.create_capture_session({
        "session_id": "stale_running",
        "camera_id": "c922_node2_gate",
        "profile": "mjpeg_720p30",
        "transport": "timed_jpeg_udp",
        "device": "/dev/video0",
        "node1_ip": "192.168.29.20",
        "node2_ip": "192.168.29.188",
        "udp_port": 5001,
        "duration_sec": 20,
        "status": "running",
        "dataset_path": str(dataset_root / "stale_running"),
    })

    CaptureSessionManager(db, SecurityPolicy(str(policy_path)))
    row = db.get_capture_session("stale_running")
    assert row is not None
    assert row["status"] == "failed"
    assert "stale active capture session" in row["error"]
    assert db.get_active_capture_session("c922_node2_gate") is None
