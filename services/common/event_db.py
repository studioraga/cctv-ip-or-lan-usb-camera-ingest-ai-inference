from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.common.migrations import apply_migrations


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class EventDB:
    """Shared SQLite access layer for the receiver and API.

    This class is the single schema authority. It applies immutable SQL migrations
    and enables foreign keys and a busy timeout on every connection.
    """

    def __init__(self, db_path: str, migrations_dir: str = "migrations"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA journal_mode = WAL")
        apply_migrations(self.conn, migrations_dir)

    def close(self) -> None:
        self.conn.close()

    def upsert_camera(self, camera_id: str, name: str, type_: str, source: str,
                      location: str = "", enabled: bool = True) -> None:
        self.conn.execute(
            """
            INSERT INTO cameras(camera_id,name,type,source,location,enabled,created_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(camera_id) DO UPDATE SET
                name=excluded.name,
                type=excluded.type,
                source=excluded.source,
                location=excluded.location,
                enabled=excluded.enabled
            """,
            (camera_id, name, type_, source, location, 1 if enabled else 0, now_iso()),
        )
        self.conn.commit()

    def list_cameras(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM cameras ORDER BY camera_id")]

    def insert_event(self, event: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO events(
                event_id,camera_id,clip_id,ts,event_type,severity,label,confidence,
                track_id,zone_id,bbox_json,attrs_json,caption,embedding_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event["event_id"], event["camera_id"], event.get("clip_id"), event["ts"],
                event["event_type"], event.get("severity", "info"), event.get("label"),
                event.get("confidence"), event.get("track_id"), event.get("zone_id"),
                json.dumps(event.get("bbox")) if event.get("bbox") is not None else None,
                json.dumps(event.get("attrs", {})), event.get("caption"),
                event.get("embedding_id"), now_iso(),
            ),
        )
        self.conn.commit()

    def insert_clip(self, clip: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO clips(
                clip_id,camera_id,start_ts,end_ts,path,keyframe_path,duration_sec,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                clip["clip_id"], clip["camera_id"], clip["start_ts"], clip["end_ts"],
                clip["path"], clip.get("keyframe_path"), clip.get("duration_sec"), now_iso(),
            ),
        )
        self.conn.commit()

    def list_events(self, camera_id: Optional[str] = None,
                    event_type: Optional[str] = None,
                    start_ts: Optional[str] = None,
                    end_ts: Optional[str] = None,
                    limit: int = 100) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM events WHERE 1=1"
        args: list[Any] = []
        if camera_id:
            sql += " AND camera_id=?"; args.append(camera_id)
        if event_type:
            sql += " AND event_type=?"; args.append(event_type)
        if start_ts:
            sql += " AND ts>=?"; args.append(start_ts)
        if end_ts:
            sql += " AND ts<=?"; args.append(end_ts)
        sql += " ORDER BY ts DESC LIMIT ?"; args.append(limit)
        return [self._decode_event(dict(r)) for r in self.conn.execute(sql, args)]

    @staticmethod
    def _decode_event(data: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("bbox_json", "attrs_json"):
            if data.get(key):
                try:
                    data[key.removesuffix("_json")] = json.loads(data[key])
                except json.JSONDecodeError:
                    data[key.removesuffix("_json")] = None
        return data

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        return self._decode_event(dict(row)) if row else None

    def list_clips(self, camera_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if camera_id:
            rows = self.conn.execute(
                "SELECT * FROM clips WHERE camera_id=? ORDER BY start_ts DESC LIMIT ?",
                (camera_id, limit),
            )
        else:
            rows = self.conn.execute("SELECT * FROM clips ORDER BY start_ts DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def get_clip(self, clip_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM clips WHERE clip_id=?", (clip_id,)).fetchone()
        return dict(row) if row else None

    def get_event_keyframe(self, event_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT e.event_id, e.camera_id, e.clip_id, c.keyframe_path
            FROM events e
            LEFT JOIN clips c ON c.clip_id=e.clip_id
            WHERE e.event_id=?
            """,
            (event_id,),
        ).fetchone()
        return dict(row) if row and row["keyframe_path"] else None

    def audit_media_access(self, media_type: str, media_id: str, outcome: str,
                           requester_ip: Optional[str], camera_id: Optional[str] = None,
                           reason: Optional[str] = None,
                           resolved_path: Optional[str] = None) -> None:
        self.conn.execute(
            """
            INSERT INTO media_access_audit(
                access_id,media_type,media_id,camera_id,requester_ip,outcome,
                reason,resolved_path,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                uuid.uuid4().hex, media_type, media_id, camera_id, requester_ip,
                outcome, reason, resolved_path, now_iso(),
            ),
        )
        self.conn.commit()
