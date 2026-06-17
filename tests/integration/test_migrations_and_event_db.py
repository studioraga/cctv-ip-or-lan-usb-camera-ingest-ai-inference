from pathlib import Path

from services.common.event_db import EventDB


def test_migrations_are_idempotent_and_media_lookup_uses_ids(tmp_path: Path):
    db_path = tmp_path / "events.db"
    migrations = Path(__file__).parents[2] / "migrations"
    db = EventDB(str(db_path), str(migrations))
    db.upsert_camera("cam1", "Camera 1", "usb_rtp", "10.0.0.2", "gate", True)

    clip_path = tmp_path / "clips" / "clip1.mp4"
    clip_path.parent.mkdir()
    clip_path.write_bytes(b"video")
    keyframe_path = tmp_path / "keyframes" / "evt1.jpg"
    keyframe_path.parent.mkdir()
    keyframe_path.write_bytes(b"jpeg")

    db.insert_clip({
        "clip_id": "clip1", "camera_id": "cam1",
        "start_ts": "2026-01-01T00:00:00+00:00",
        "end_ts": "2026-01-01T00:00:02+00:00",
        "path": str(clip_path), "keyframe_path": str(keyframe_path),
        "duration_sec": 2.0,
    })
    db.insert_event({
        "event_id": "evt1", "camera_id": "cam1", "clip_id": "clip1",
        "ts": "2026-01-01T00:00:01+00:00", "event_type": "motion_detected",
        "severity": "info", "attrs": {},
    })

    assert db.get_clip("clip1")["path"] == str(clip_path)
    assert db.get_event_keyframe("evt1")["keyframe_path"] == str(keyframe_path)
    db.audit_media_access("clip", "clip1", "allowed", "127.0.0.1", "cam1",
                          resolved_path=str(clip_path))
    count = db.conn.execute("SELECT COUNT(*) FROM media_access_audit").fetchone()[0]
    assert count == 1
    db.close()

    # A second open verifies migration idempotence and hash history.
    db2 = EventDB(str(db_path), str(migrations))
    versions = db2.conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    assert [row[0] for row in versions] == [1, 2, 3]
    db2.close()
