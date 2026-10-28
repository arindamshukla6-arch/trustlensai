"""Face detection and embedding backends.

Preferred: OpenCV YuNet (detector, MIT licence) + OpenCV SFace (recogniser,
Apache-2.0) from the OpenCV Model Zoo. Run `python scripts/download_models.py`
to fetch them (about 37 MB, CPU only).

Fallback: OpenCV's bundled Haar cascade for *detection only*. Haar cannot
produce embeddings, so face matching is reported as NOT RUN — it is never
simulated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ..config import settings

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"


@dataclass
class Face:
    box: tuple[int, int, int, int]  # x, y, w, h
    score: Optional[float]
    raw: Optional[np.ndarray] = field(default=None, repr=False)  # YuNet row (with landmarks)

    @property
    def size(self) -> int:
        return min(self.box[2], self.box[3])

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.box
        return x + w / 2, y + h / 2


def yunet_path() -> Path:
    return settings.models_dir / YUNET_FILE


def sface_path() -> Path:
    return settings.models_dir / SFACE_FILE


@lru_cache(maxsize=1)
def _haar():
    # OpenCV 5 removed CascadeClassifier from the main package; fail cleanly.
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return None
    try:
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        clf = cv2.CascadeClassifier(str(path))
    except Exception:
        return None
    return None if clf.empty() else clf


@lru_cache(maxsize=1)
def _yunet():
    p = yunet_path()
    if not p.exists() or not hasattr(cv2, "FaceDetectorYN"):
        return None
    try:
        return cv2.FaceDetectorYN.create(str(p), "", (320, 320), 0.7, 0.3, 5000)
    except cv2.error:
        return None


@lru_cache(maxsize=1)
def _sface():
    p = sface_path()
    if not p.exists() or not hasattr(cv2, "FaceRecognizerSF"):
        return None
    try:
        return cv2.FaceRecognizerSF.create(str(p), "")
    except cv2.error:
        return None


def detector_name() -> str:
    if _yunet() is not None:
        return "OpenCV YuNet (2023mar)"
    if _haar() is not None:
        return "OpenCV Haar cascade (fallback, lower accuracy)"
    return "none"


def embedding_available() -> bool:
    return _yunet() is not None and _sface() is not None


def capability_report() -> dict:
    return {
        "detector": detector_name(),
        "embedding_model": "OpenCV SFace (2021dec)" if embedding_available() else "not installed",
        "face_matching_available": embedding_available(),
        "models_dir": str(settings.models_dir),
    }


def detect(bgr: np.ndarray) -> list[Face]:
    yn = _yunet()
    if yn is not None:
        h, w = bgr.shape[:2]
        yn.setInputSize((w, h))
        _, faces = yn.detect(bgr)
        if faces is None:
            return []
        return [Face(tuple(int(v) for v in f[:4]), float(f[14]), f) for f in faces]
    haar = _haar()
    if haar is None:
        return []
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    boxes = haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40))
    return [Face(tuple(int(v) for v in b), None) for b in boxes]


def embed(bgr: np.ndarray, face: Face) -> np.ndarray:
    rec = _sface()
    if rec is None or face.raw is None:
        raise RuntimeError("Embedding model not available.")
    aligned = rec.alignCrop(bgr, face.raw)
    return rec.feature(aligned)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    rec = _sface()
    return float(rec.match(a, b, cv2.FaceRecognizerSF_FR_COSINE))
