from services.node1_api_gateway.schemas import Node2MotionEventRequest


def _dump(value):
    return value.model_dump() if hasattr(value, "model_dump") else value.dict()


def test_node2_motion_event_accepts_detection_evidence():
    req = Node2MotionEventRequest(
        camera_id="c922_node2_gate",
        profile="mjpeg_720p30",
        detections=[{"label": "person", "confidence": 0.91, "bbox_xyxy": [1, 2, 3, 4], "class_id": 0}],
        trigger_frame_id=42,
        trigger_wall_ns=123456789,
        cooldown_sec=20,
    )
    data = _dump(req)
    assert data["event_type"] == "motion_detected"
    assert data["detections"][0]["label"] == "person"
    assert data["trigger_frame_id"] == 42
