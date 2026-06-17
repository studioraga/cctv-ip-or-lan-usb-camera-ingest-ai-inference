from pathlib import Path

from services.common.event_db import EventDB


def test_capture_session_tables_and_artifacts(tmp_path: Path):
    db = EventDB(str(tmp_path / "events.db"), str(Path(__file__).parents[2] / "migrations"))
    db.upsert_camera("cam1", "Camera 1", "usb", "10.0.0.2")
    db.create_capture_session({
        "session_id": "cap1",
        "camera_id": "cam1",
        "profile": "mjpeg_720p30",
        "transport": "timed_jpeg_udp",
        "device": "/dev/video0",
        "node1_ip": "10.0.0.1",
        "node2_ip": "10.0.0.2",
        "udp_port": 5001,
        "duration_sec": 10,
        "status": "pending",
        "dataset_path": str(tmp_path / "datasets" / "cap1"),
    })
    assert db.get_active_capture_session("cam1")["session_id"] == "cap1"
    db.update_capture_session("cap1", status="completed", frames_written=3, bytes_written=100)
    assert db.get_active_capture_session("cam1") is None
    assert db.get_capture_session("cap1")["frames_written"] == 3
    artifact_path = tmp_path / "datasets" / "cap1" / "manifest.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("{}")
    db.insert_capture_artifact({
        "artifact_id": "a1",
        "session_id": "cap1",
        "artifact_type": "manifest",
        "path": str(artifact_path),
        "media_type": "application/json",
        "size_bytes": artifact_path.stat().st_size,
        "sha256": "abc",
    })
    assert db.list_capture_artifacts("cap1")[0]["artifact_type"] == "manifest"
    db.close()
