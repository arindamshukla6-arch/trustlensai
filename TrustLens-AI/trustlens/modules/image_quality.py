"""Simple, explainable image quality measurements."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..config import settings
from ..models import Quality


@dataclass
class QualityReport:
    width: int
    height: int
    brightness: float
    sharpness: float
    issues: list[str]

    @property
    def quality(self) -> Quality:
        if self.issues:
            return Quality.POOR
        if self.sharpness < settings.min_sharpness * 2:
            return Quality.ADEQUATE
        return Quality.GOOD

    def as_dict(self) -> dict:
        return {"width": self.width, "height": self.height,
                "brightness": round(self.brightness, 1), "sharpness": round(self.sharpness, 1),
                "issues": self.issues}


def measure(bgr: np.ndarray) -> QualityReport:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    h, w = gray.shape[:2]
    brightness = float(gray.mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    issues = []
    if brightness < settings.min_brightness:
        issues.append(f"Too dark (mean brightness {brightness:.0f}/255).")
    if brightness > settings.max_brightness:
        issues.append(f"Over-exposed (mean brightness {brightness:.0f}/255).")
    if sharpness < settings.min_sharpness:
        issues.append(f"Blurry (sharpness {sharpness:.0f}, minimum {settings.min_sharpness:.0f}).")
    if min(h, w) < 240:
        issues.append(f"Low resolution ({w}x{h}).")
    return QualityReport(w, h, brightness, sharpness, issues)


def read_image(path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)  # works with non-ASCII Windows paths
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("The image could not be decoded.")
    return img
