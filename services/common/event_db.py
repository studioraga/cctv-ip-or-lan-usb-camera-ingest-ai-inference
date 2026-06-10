from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cameras (
    camera_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    location TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    clip_id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    path TEXT NOT NULL,
    keyframe_path TEXT,
    duration_sec REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    clip_id TEXT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    label TEXT,
    confidence REAL,
    track_id TEXT,
    zone_id TEXT,
    bbox_json TEXT,
    attrs_json TEXT,
    caption TEXT,
    embedding_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_camera_ts ON events(camera_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts);
CREATE INDEX IF NOT EXISTS idx_events_zone_ts ON events(zone_id, ts);
"""


class EventDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def upsert_camera(self, camera_id: str, name: str, type_: str, source: str, location: str = "", enabled: bool = True) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cameras(camera_id,name,type,source,location,enabled,created_at) VALUES(?,?,?,?,?,?,?)",
            (camera_id, name, type_, source, location, 1 if enabled else 0, now_iso()),
        )
        self.conn.commit()

    def list_cameras(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM cameras ORDER BY camera_id")]

    def insert_event(self, event: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO events(event_id,camera_id,clip_id,ts,event_type,severity,label,confidence,track_id,zone_id,bbox_json,attrs_json,caption,embedding_id,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event["event_id"], event["camera_id"], event.get("clip_id"), event["ts"], event["event_type"],
                event.get("severity", "info"), event.get("label"), event.get("confidence"), event.get("track_id"), event.get("zone_id"),
                json.dumps(event.get("bbox")) if event.get("bbox") is not None else None,
                json.dumps(event.get("attrs", {})), event.get("caption"), event.get("embedding_id"), now_iso(),
            ),
        )
        self.conn.commit()

    def list_events(self, camera_id: Optional[str] = None, event_type: Optional[str] = None, start_ts: Optional[str] = None, end_ts: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM events WHERE 1=1"
        args = []
        if camera_id:
            sql += " AND camera_id=?"; args.append(camera_id)
        if event_type:
            sql += " AND event_type=?"; args.append(event_type)
        if start_ts:
            sql += " AND ts>=?"; args.append(start_ts)
        if end_ts:
            sql += " AND ts<=?"; args.append(end_ts)
        sql += " ORDER BY ts DESC LIMIT ?"; args.append(limit)
        rows = []
        for r in self.conn.execute(sql, args):
            d = dict(r)
            for key in ("bbox_json", "attrs_json"):
                if d.get(key):
                    try: d[key.replace("_json", "")] = json.loads(d[key])
                    except json.JSONDecodeError: pass
            rows.append(d)
        return rows

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        return dict(row) if row else None

    def list_clips(self, camera_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if camera_id:
            return [dict(r) for r in self.conn.execute("SELECT * FROM clips WHERE camera_id=? ORDER BY start_ts DESC LIMIT ?", (camera_id, limit))]
        return [dict(r) for r in self.conn.execute("SELECT * FROM clips ORDER BY start_ts DESC LIMIT ?", (limit,))]
