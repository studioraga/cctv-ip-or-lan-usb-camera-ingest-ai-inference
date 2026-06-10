from __future__ import annotations
import cv2
import numpy as np

class MotionDetector:
    def __init__(self, threshold: float = 12.0):
        self.threshold = threshold
        self.prev = None

    def detect(self, frame_bgr):
        gray = cv2.cvtColor(cv2.resize(frame_bgr, (320, 180)), cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if self.prev is None:
            self.prev = gray
            return []
        diff = cv2.absdiff(self.prev, gray)
        self.prev = gray
        score = float(np.mean(diff))
        if score >= self.threshold:
            return [{"label": "motion", "confidence": min(score / self.threshold, 1.0), "attrs": {"motion_score": score}}]
        return []
