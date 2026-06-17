PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS capture_sessions (
    session_id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    requested_by TEXT,
    requested_source TEXT,
    profile TEXT NOT NULL,
    transport TEXT NOT NULL CHECK (transport IN ('rtp', 'timed_jpeg_udp')),
    device TEXT NOT NULL,
    node1_ip TEXT NOT NULL,
    node2_ip TEXT NOT NULL,
    udp_port INTEGER NOT NULL CHECK (udp_port >= 1 AND udp_port <= 65535),
    duration_sec INTEGER NOT NULL CHECK (duration_sec >= 1 AND duration_sec <= 7200),
    status TEXT NOT NULL CHECK (status IN ('pending','running','completed','failed','cancelled')),
    dataset_path TEXT NOT NULL,
    manifest_path TEXT,
    started_at TEXT,
    ended_at TEXT,
    error TEXT,
    frames_written INTEGER NOT NULL DEFAULT 0,
    bytes_written INTEGER NOT NULL DEFAULT 0,
    dropped_frames INTEGER NOT NULL DEFAULT 0,
    frame_stride INTEGER NOT NULL DEFAULT 1 CHECK (frame_stride >= 1),
    max_bytes INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(camera_id) REFERENCES cameras(camera_id)
);

CREATE INDEX IF NOT EXISTS idx_capture_sessions_camera_created
    ON capture_sessions(camera_id, created_at);
CREATE INDEX IF NOT EXISTS idx_capture_sessions_status
    ON capture_sessions(status);

CREATE TABLE IF NOT EXISTS capture_artifacts (
    artifact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    media_type TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES capture_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_capture_artifacts_session
    ON capture_artifacts(session_id);
