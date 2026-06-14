PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cameras (
    camera_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    location TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
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
    created_at TEXT NOT NULL,
    FOREIGN KEY(camera_id) REFERENCES cameras(camera_id)
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
    created_at TEXT NOT NULL,
    FOREIGN KEY(camera_id) REFERENCES cameras(camera_id),
    FOREIGN KEY(clip_id) REFERENCES clips(clip_id)
);

CREATE INDEX IF NOT EXISTS idx_events_camera_ts ON events(camera_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts);
CREATE INDEX IF NOT EXISTS idx_events_zone_ts ON events(zone_id, ts);
CREATE INDEX IF NOT EXISTS idx_clips_camera_start ON clips(camera_id, start_ts);
