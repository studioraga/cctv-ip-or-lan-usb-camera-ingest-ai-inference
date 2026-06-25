# import numpy as np
import pytest

np = pytest.importorskip("numpy", reason="YOLO ONNX tests require numpy; install Node1 inference deps to run them")
pytest.importorskip("cv2", reason="YOLO ONNX tests require OpenCV; run on Node1 or install OpenCV")


from services.node1_inference_worker.detectors.yolo_onnx import (
    LetterboxMeta,
    decode_yolo_output,
    letterbox,
    nms,
)


def test_letterbox_preserves_aspect_ratio():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    out, meta = letterbox(frame, 640)
    assert out.shape == (640, 640, 3)
    assert meta.ratio == 1.0
    assert meta.pad_top == 80
    assert meta.pad_left == 0


def test_decode_yolov5_style_output_and_nms():
    meta = LetterboxMeta(original_shape=(480, 640), input_shape=(640, 640), ratio=1.0, pad_left=0.0, pad_top=80.0)
    # cx,cy,w,h,obj, class0, class1. Two overlapping person boxes; one lower score.
    pred = np.array([
        [320, 320, 100, 120, 0.9, 0.9, 0.1],
        [322, 322, 100, 120, 0.8, 0.9, 0.1],
        [100, 120, 50, 60, 0.7, 0.1, 0.9],
    ], dtype=np.float32)[None, :, :]
    dets = decode_yolo_output([pred], meta, class_names=["person", "vehicle"], confidence_threshold=0.25, iou_threshold=0.5)
    assert len(dets) == 2
    assert dets[0].label == "person"
    assert dets[0].confidence > dets[1].confidence
    assert dets[1].label == "vehicle"
    # Top padding is removed when mapping to original image.
    x1, y1, x2, y2 = dets[0].bbox_xyxy
    assert 260 <= x1 <= 280
    assert 170 <= y1 <= 190
    assert 360 <= x2 <= 380
    assert 280 <= y2 <= 310


def test_decode_yolov8_transposed_output():
    meta = LetterboxMeta(original_shape=(640, 640), input_shape=(640, 640), ratio=1.0, pad_left=0.0, pad_top=0.0)
    # Shape: (1, 4 + classes, N). No objectness.
    pred = np.zeros((1, 6, 2), dtype=np.float32)
    pred[0, :, 0] = [100, 100, 40, 40, 0.2, 0.95]
    pred[0, :, 1] = [200, 200, 50, 50, 0.9, 0.1]
    dets = decode_yolo_output([pred], meta, class_names=["a", "b"], confidence_threshold=0.5, iou_threshold=0.5)
    assert len(dets) == 2
    assert dets[0].label == "b"
    assert dets[1].label == "a"


def test_decode_yolov8_yolo11_coco_person_class0_output():
    meta = LetterboxMeta(original_shape=(640, 640), input_shape=(640, 640), ratio=1.0, pad_left=0.0, pad_top=0.0)
    # YOLOv8/YOLO11 COCO layout: (1, 4 + 80 classes, N).
    # Column 4 is class 0 = person, not YOLOv5 objectness.
    pred = np.zeros((1, 84, 1), dtype=np.float32)
    pred[0, 0:4, 0] = [320, 320, 100, 100]
    pred[0, 4, 0] = 0.95
    class_names = ["person"] + [f"class_{i}" for i in range(1, 80)]

    dets = decode_yolo_output([pred], meta, class_names=class_names, confidence_threshold=0.25, iou_threshold=0.45)

    assert len(dets) == 1
    assert dets[0].label == "person"
    assert dets[0].class_id == 0
    assert dets[0].confidence == pytest.approx(0.95, rel=1e-5)


def test_nms_suppresses_overlapping_boxes():
    boxes = np.array([[0, 0, 100, 100], [10, 10, 110, 110], [200, 200, 260, 260]], dtype=np.float32)
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    assert nms(boxes, scores, 0.5) == [0, 2]
