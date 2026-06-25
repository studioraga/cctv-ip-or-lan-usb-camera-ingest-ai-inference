from services.node2_motion_watcher.watcher import (
    DetectionDebouncer,
    WatcherConfig,
    build_motion_event_payload,
    config_from_args,
    normalize_detection,
    parse_args,
    synthetic_detection,
)


def test_node2_motion_payload_contains_trigger_evidence():
    cfg = WatcherConfig(
        node1_url="http://192.0.2.21:8080",
        camera_id="c922_node2_gate",
        profile="mjpeg_720p30",
        device="/dev/video0",
        duration_sec=90,
        udp_port=5001,
    )
    payload = build_motion_event_payload(
        cfg,
        motion_score=18.5,
        detections=synthetic_detection(),
        trigger_frame_id=123,
    )
    assert payload["event_type"] == "motion_detected"
    assert payload["duration_sec"] == 90
    assert payload["motion_source"] == "node2_yolo_motion_watcher"
    assert payload["trigger_frame_id"] == 123
    assert payload["detections"][0]["label"] == "person"
    assert payload["detections"][0]["class_id"] == 0


def test_detection_debouncer_requires_k_hits_inside_window():
    debouncer = DetectionDebouncer(window=5, required=2)
    assert not debouncer.update([])
    assert not debouncer.update([{"label": "person", "confidence": 0.8}])
    assert debouncer.update([{"label": "person", "confidence": 0.9}])
    debouncer.reset()
    assert not debouncer.update([])


def test_normalize_detection_accepts_existing_yolo_attrs():
    det = {"label": "person", "confidence": 0.9, "bbox_xyxy": [1, 2, 3, 4], "attrs": {"class_id": 0}}
    out = normalize_detection(det)
    assert out == {"label": "person", "confidence": 0.9, "bbox_xyxy": [1.0, 2.0, 3.0, 4.0], "class_id": 0}


def test_cli_args_override_env_config():
    args = parse_args([
        "--node1-url", "http://192.0.2.21:8080/",
        "--profile", "mjpeg_480p30",
        "--duration-sec", "30",
        "--no-require-yolo",
        "--synthetic-trigger",
    ])
    cfg = config_from_args(args)
    assert cfg.node1_url == "http://192.0.2.21:8080"
    assert cfg.profile == "mjpeg_480p30"
    assert cfg.duration_sec == 30
    assert cfg.yolo_required is False


def test_cli_args_override_watcher_tuning():
    args = parse_args([
        "--node1-url", "http://192.0.2.21:8080/",
        "--yolo-confidence", "0.25",
        "--yolo-iou", "0.40",
        "--required-confirmations", "1",
        "--candidate-window", "3",
        "--cooldown-sec", "5",
        "--classes", "person,dog",
        "--camera-release-grace-sec", "0.1",
        "--synthetic-trigger",
    ])
    cfg = config_from_args(args)
    assert cfg.yolo_confidence_threshold == 0.25
    assert cfg.yolo_iou_threshold == 0.40
    assert cfg.required_confirmations == 1
    assert cfg.candidate_window == 3
    assert cfg.cooldown_sec == 5
    assert cfg.interesting_labels == ("person", "dog")
    assert cfg.camera_release_grace_sec == 0.1
