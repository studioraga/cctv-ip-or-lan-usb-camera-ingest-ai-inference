from __future__ import annotations

import queue
import shutil
import threading
from pathlib import Path

from services.common.event_db import EventDB
from services.common.policy import SecurityPolicy
from services.node1_api_gateway.schemas import CaptureSessionRequest
from services.node1_capture_orchestrator.session_manager import CaptureSessionManager


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


def test_start_session_returns_without_self_lock_deadlock(tmp_path: Path, monkeypatch):
    """Regression test for the Step 14 motion-event POST hang.

    start_session() used to call get_session() while still holding its internal
    mutex. Because get_session() also takes that mutex to merge live progress,
    the API thread deadlocked before returning the session_id to curl.
    """
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for source in (Path(__file__).parents[2] / "migrations").glob("*.sql"):
        shutil.copy2(source, migrations / source.name)

    dataset_root = tmp_path / "datasets"
    policy_path = tmp_path / "policy.yaml"
    _write_policy(policy_path, dataset_root)

    monkeypatch.setenv("AI_CAMERA_NODE1_IP", "192.168.29.20")
    monkeypatch.setenv("AI_CAMERA_NODE2_IP", "192.168.29.188")
    monkeypatch.setenv("AI_CAMERA_NODE2_API_PORT", "8082")
    monkeypatch.setenv("AI_CAMERA_CAPTURE_UDP_PORT", "5001")
    monkeypatch.setenv("AI_CAMERA_DATASET_ROOT", str(dataset_root))

    db = EventDB(str(tmp_path / "events.db"), str(migrations))
    db.upsert_camera("c922_node2_gate", "cam", "usb", "192.168.29.188")
    policy = SecurityPolicy(str(policy_path))
    manager = CaptureSessionManager(db, policy)

    # Avoid real UDP/Node2 work; this test only verifies the synchronous API
    # path returns instead of deadlocking while the background thread is started.
    monkeypatch.setattr(manager, "_run_session", lambda cfg, stop_event: None)

    req = CaptureSessionRequest(
        camera_id="c922_node2_gate",
        profile="mjpeg_720p30",
        duration_sec=1,
        device="/dev/video0",
        transport="timed_jpeg_udp",
        udp_port=5001,
        dataset_mode="source_jpeg",
        requested_by="test",
    )

    result_q: queue.Queue[object] = queue.Queue()

    def call_start() -> None:
        try:
            result_q.put(manager.start_session(req, requested_source="127.0.0.1"))
        except Exception as exc:  # pragma: no cover - surfaced below
            result_q.put(exc)

    t = threading.Thread(target=call_start, daemon=True)
    t.start()
    t.join(timeout=2.0)
    assert not t.is_alive(), "start_session deadlocked while returning the created session"

    result = result_q.get_nowait()
    if isinstance(result, Exception):
        raise result
    assert result["session_id"].startswith("cap_")
    assert result["status"] == "pending"
    assert result["frames_written"] == 0
    assert result["dataset_path"]
