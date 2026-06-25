from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import cv2
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None


@dataclass(frozen=True)
class LetterboxMeta:
    original_shape: tuple[int, int]
    input_shape: tuple[int, int]
    ratio: float
    pad_left: float
    pad_top: float


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    class_id: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "confidence": float(self.confidence),
            "bbox_xyxy": [float(v) for v in self.bbox_xyxy],
            "attrs": {"class_id": int(self.class_id)},
        }


def letterbox(frame_bgr: np.ndarray, input_size: int | tuple[int, int]) -> tuple[np.ndarray, LetterboxMeta]:
    if isinstance(input_size, int):
        target_h = target_w = input_size
    else:
        target_w, target_h = int(input_size[0]), int(input_size[1])
    if target_w <= 0 or target_h <= 0:
        raise ValueError("input_size must be positive")
    h, w = frame_bgr.shape[:2]
    ratio = min(target_w / w, target_h / h)
    new_w = int(round(w * ratio))
    new_h = int(round(h * ratio))
    resized = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
    pad_left = (target_w - new_w) // 2
    pad_top = (target_h - new_h) // 2
    canvas[pad_top:pad_top + new_h, pad_left:pad_left + new_w] = resized
    return canvas, LetterboxMeta((h, w), (target_h, target_w), ratio, float(pad_left), float(pad_top))


def _xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    out = np.empty_like(boxes, dtype=np.float32)
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
    return out


def scale_boxes_to_original(boxes_xyxy: np.ndarray, meta: LetterboxMeta) -> np.ndarray:
    boxes = boxes_xyxy.astype(np.float32).copy()
    boxes[:, [0, 2]] -= meta.pad_left
    boxes[:, [1, 3]] -= meta.pad_top
    boxes[:, :4] /= meta.ratio
    h, w = meta.original_shape
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w - 1)
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h - 1)
    return boxes


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter_w = np.maximum(0, xx2 - xx1)
        inter_h = np.maximum(0, yy2 - yy1)
        inter = inter_w * inter_h
        union = areas[i] + areas[rest] - inter
        iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
        order = rest[iou <= iou_threshold]
    return keep


def _normalize_output(raw: np.ndarray) -> np.ndarray:
    arr = np.asarray(raw)
    if arr.ndim == 3 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim != 2:
        raise ValueError(f"unsupported YOLO output shape: {arr.shape}")
    # YOLOv8/YOLO11 ONNX commonly returns (4 + classes, N), for example
    # (84, 8400) for COCO.  YOLOv5 commonly returns (N, 5 + classes), for
    # example (8400, 85).  Normalize both to (N, columns).
    if arr.shape[0] in range(5, 200) and (arr.shape[0] < arr.shape[1] or arr.shape[1] < 6):
        arr = arr.T
    return arr.astype(np.float32, copy=False)


def _infer_yolo_layout(column_count: int, class_count: int | None) -> str:
    """Return output layout for normalized YOLO rows.

    Layout inference must not rely on score values.  YOLOv8/YOLO11 class
    scores are also in [0, 1], so a value-based heuristic can accidentally
    treat class-0 score as YOLOv5 objectness and shift all class IDs.
    """
    if class_count and column_count == 4 + class_count:
        return "yolov8"
    if class_count and column_count == 5 + class_count:
        return "yolov5"
    if column_count == 84:
        return "yolov8"  # COCO: 4 box columns + 80 class scores.
    if column_count == 85:
        return "yolov5"  # COCO: 4 box columns + objectness + 80 class scores.
    if column_count > 6 and (column_count - 4) in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 80}:
        return "yolov8"
    if column_count > 6:
        return "yolov5"
    return "yolov8"


def decode_yolo_output(
    outputs: Sequence[np.ndarray],
    meta: LetterboxMeta,
    class_names: Sequence[str] | None = None,
    confidence_threshold: float = 0.25,
    iou_threshold: float = 0.45,
) -> list[Detection]:
    if not outputs:
        return []
    pred = _normalize_output(np.asarray(outputs[0]))
    if pred.shape[1] < 6:
        raise ValueError(f"YOLO output must have at least 6 columns, got {pred.shape}")

    class_count = len(class_names) if class_names else None

    # Already postprocessed format: x1,y1,x2,y2,score,class_id.
    # A 6-column tensor can also mean YOLOv8 with two classes
    # (cx,cy,w,h,c0,c1), so only treat it as postprocessed when class_id
    # looks integer-like and no class-name count points to a 2-class model.
    if (
        pred.shape[1] == 6
        and not (class_count and pred.shape[1] == 4 + class_count)
        and np.allclose(pred[:, 5], np.round(pred[:, 5]), atol=1e-4)
    ):
        boxes_xyxy = pred[:, :4]
        scores = pred[:, 4]
        class_ids = pred[:, 5].astype(np.int64)
    else:
        boxes_xyxy = _xywh_to_xyxy(pred[:, :4])
        layout = _infer_yolo_layout(pred.shape[1], class_count)
        remaining = pred[:, 4:]
        if layout == "yolov5":
            obj = remaining[:, 0]
            cls_scores = remaining[:, 1:]
            class_ids = cls_scores.argmax(axis=1).astype(np.int64)
            scores = obj * cls_scores[np.arange(len(cls_scores)), class_ids]
        else:
            cls_scores = remaining
            class_ids = cls_scores.argmax(axis=1).astype(np.int64)
            scores = cls_scores[np.arange(len(cls_scores)), class_ids]

    mask = scores >= confidence_threshold
    boxes_xyxy = boxes_xyxy[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]
    if len(boxes_xyxy) == 0:
        return []

    boxes_xyxy = scale_boxes_to_original(boxes_xyxy, meta)
    keep_all: list[int] = []
    for cls in np.unique(class_ids):
        idx = np.where(class_ids == cls)[0]
        keep = nms(boxes_xyxy[idx], scores[idx], iou_threshold)
        keep_all.extend(idx[k] for k in keep)
    keep_all.sort(key=lambda i: float(scores[i]), reverse=True)

    detections: list[Detection] = []
    for i in keep_all:
        cls = int(class_ids[i])
        label = class_names[cls] if class_names and 0 <= cls < len(class_names) else str(cls)
        detections.append(Detection(label=label, confidence=float(scores[i]), bbox_xyxy=tuple(float(v) for v in boxes_xyxy[i]), class_id=cls))
    return detections


class YoloOnnxDetector:
    """YOLO ONNX detector with generic YOLOv5/YOLOv8-style post-processing.

    Supported output layouts:
      - YOLOv5-style: (1, N, 5 + classes), where columns are cx,cy,w,h,obj,classes...
      - YOLOv8-style: (1, 4 + classes, N) or (1, N, 4 + classes)
      - Already postprocessed: (N, 6), x1,y1,x2,y2,score,class_id
    """

    def __init__(
        self,
        model_path: str,
        input_size: int | tuple[int, int] = 640,
        providers=None,
        class_names: Sequence[str] | None = None,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ):
        if ort is None:
            raise RuntimeError("onnxruntime is not installed")
        if not Path(model_path).exists():
            raise FileNotFoundError(model_path)
        self.model_path = model_path
        self.input_size = input_size
        self.class_names = list(class_names or [])
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self._last_meta: LetterboxMeta | None = None
        providers = providers or ort.get_available_providers()
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    def preprocess(self, frame_bgr):
        img, meta = letterbox(frame_bgr, self.input_size)
        self._last_meta = meta
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))[None, ...]
        return np.ascontiguousarray(img)

    def detect(self, frame_bgr) -> List[Dict[str, Any]]:
        tensor = self.preprocess(frame_bgr)
        outputs = self.session.run(None, {self.input_name: tensor})
        return self.postprocess(outputs, frame_bgr.shape)

    def postprocess(self, outputs, frame_shape) -> List[Dict[str, Any]]:
        meta = self._last_meta
        if meta is None:
            h, w = frame_shape[:2]
            meta = LetterboxMeta((h, w), (self.input_size, self.input_size) if isinstance(self.input_size, int) else (self.input_size[1], self.input_size[0]), 1.0, 0.0, 0.0)
        detections = decode_yolo_output(outputs, meta, self.class_names, self.confidence_threshold, self.iou_threshold)
        return [d.as_dict() for d in detections]
