from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any
import cv2
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None

class YoloOnnxDetector:
    """Minimal YOLO-style ONNX detector scaffold.

    This class intentionally keeps post-processing generic because YOLO exports vary
    across versions. Replace `postprocess` with model-specific output decoding once
    the selected ONNX model is added under models/object_detection/.
    """
    def __init__(self, model_path: str, input_size: int = 640, providers=None):
        if ort is None:
            raise RuntimeError("onnxruntime is not installed")
        if not Path(model_path).exists():
            raise FileNotFoundError(model_path)
        self.model_path = model_path
        self.input_size = input_size
        providers = providers or ort.get_available_providers()
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    def preprocess(self, frame_bgr):
        img = cv2.resize(frame_bgr, (self.input_size, self.input_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))[None, ...]
        return img

    def detect(self, frame_bgr) -> List[Dict[str, Any]]:
        tensor = self.preprocess(frame_bgr)
        outputs = self.session.run(None, {self.input_name: tensor})
        return self.postprocess(outputs, frame_bgr.shape)

    def postprocess(self, outputs, frame_shape) -> List[Dict[str, Any]]:
        # Placeholder: model-specific parsing is required for production.
        return []
