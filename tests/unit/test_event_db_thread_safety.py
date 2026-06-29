from __future__ import annotations

import shutil
import threading
from pathlib import Path

from services.common.event_db import EventDB, now_iso


def test_event_db_serializes_shared_connection_access(tmp_path: Path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for source in (Path(__file__).parents[2] / "migrations").glob("*.sql"):
        shutil.copy2(source, migrations / source.name)

    db = EventDB(str(tmp_path / "events.db"), str(migrations))
    db.upsert_camera("c922_node2_gate", "cam", "usb", "192.168.29.188")

    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for j in range(20):
                db.insert_event({
                    "event_id": f"evt_{index}_{j}",
                    "camera_id": "c922_node2_gate",
                    "ts": now_iso(),
                    "event_type": "thread_safety_smoke",
                    "attrs": {"worker": index, "iteration": j},
                })
                db.list_events(camera_id="c922_node2_gate", limit=5)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    if errors:
        raise errors[0]
    assert len(db.list_events(event_type="thread_safety_smoke", limit=1000)) == 80
