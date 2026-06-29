from pathlib import Path

from services.common.event_db import EventDB
from services.node1_event_indexer.indexer import build_index, event_to_document, hash_embedding


def test_hash_embedding_is_normalized():
    vec = hash_embedding("person detected at gate", dimension=32)
    assert len(vec) == 32
    assert any(v != 0 for v in vec)


def test_event_indexer_writes_jsonl(tmp_path: Path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    source_migrations = Path(__file__).parents[2] / "migrations"
    for source in source_migrations.glob("*.sql"):
        (migrations / source.name).write_text(source.read_text())
    db_path = tmp_path / "events.db"
    cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        db = EventDB(str(db_path))
        db.upsert_camera("cam", "cam", "usb", "192.0.2.2")
        db.insert_event({"event_id": "evt", "camera_id": "cam", "ts": "2026-01-01T00:00:00+00:00", "event_type": "node2_motion_detected", "label": "motion", "attrs": {"detections": [{"label": "person", "confidence": 0.9}]}})
        out = tmp_path / "index.jsonl"
        result = build_index(str(db_path), output_path=str(out), dimension=32)
    finally:
        os.chdir(cwd)
    assert result["documents"] == 1
    assert out.read_text().count("event:evt") == 1
