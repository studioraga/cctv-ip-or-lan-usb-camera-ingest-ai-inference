"""Compatibility wrapper for the shared YOLO ONNX detector.

The implementation currently lives in the Node1 inference worker package because
it was introduced during Step 12.  New Node2 motion-watcher code imports through
this shared namespace so the implementation can be moved later without changing
Node2 call sites.
"""
from services.node1_inference_worker.detectors.yolo_onnx import (  # noqa: F401
    Detection,
    LetterboxMeta,
    YoloOnnxDetector,
    decode_yolo_output,
    letterbox,
    nms,
    scale_boxes_to_original,
)
