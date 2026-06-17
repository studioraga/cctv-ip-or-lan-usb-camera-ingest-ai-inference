from pathlib import Path

from services.node1_capture_orchestrator.dataset_writer import DatasetWriter


def test_dataset_writer_stores_source_jpegs_and_manifest(tmp_path: Path):
    writer = DatasetWriter(
        tmp_path,
        "cap_test",
        camera_id="cam1",
        profile="mjpeg_720p30",
        transport="timed_jpeg_udp",
        duration_sec=10,
        frame_stride=1,
    )
    writer.prepare()
    result = writer.write_frame(
        frame_id=1,
        jpeg=b"\xff\xd8hello\xff\xd9",
        sender_wall_ns=1_000_000_000,
        sender_monotonic_ns=2,
        receiver_wall_ns=1_020_000_000,
        fragment_count=1,
        e2e_latency_ms=20.0,
    )
    assert result.written is True
    assert (tmp_path / "cap_test" / result.relative_path).read_bytes() == b"\xff\xd8hello\xff\xd9"
    manifest = writer.finalize(status="completed")
    assert manifest["session_id"] == "cap_test"
    assert manifest["metrics"]["frames_written"] == 1
    assert (tmp_path / "cap_test" / "metadata" / "frames.jsonl").is_file()
    assert (tmp_path / "cap_test" / "artifacts" / "metrics_summary.json").is_file()
    assert (tmp_path / "cap_test" / "artifacts" / "report.md").is_file()


def test_dataset_writer_frame_stride_skips_frames(tmp_path: Path):
    writer = DatasetWriter(
        tmp_path,
        "cap_stride",
        camera_id="cam1",
        profile="mjpeg_720p30",
        transport="timed_jpeg_udp",
        duration_sec=10,
        frame_stride=2,
    )
    writer.prepare()
    r1 = writer.write_frame(frame_id=1, jpeg=b"\xff\xd8a\xff\xd9", sender_wall_ns=1, sender_monotonic_ns=1, receiver_wall_ns=2, fragment_count=1, e2e_latency_ms=1)
    r2 = writer.write_frame(frame_id=2, jpeg=b"\xff\xd8b\xff\xd9", sender_wall_ns=1, sender_monotonic_ns=1, receiver_wall_ns=2, fragment_count=1, e2e_latency_ms=1)
    assert r1.written is False
    assert r2.written is True
    assert writer.frames_written == 1
    assert writer.frames_skipped == 1
