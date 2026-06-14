PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS media_access_audit (
    access_id TEXT PRIMARY KEY,
    media_type TEXT NOT NULL CHECK (media_type IN ('clip', 'keyframe')),
    media_id TEXT NOT NULL,
    camera_id TEXT,
    requester_ip TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('allowed', 'denied', 'not_found')),
    reason TEXT,
    resolved_path TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_access_created_at
    ON media_access_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_media_access_media
    ON media_access_audit(media_type, media_id);
