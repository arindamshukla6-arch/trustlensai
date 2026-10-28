"""Reference photo vs candidate capture comparison using real embeddings."""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..config import settings
from ..models import Finding, Quality, Signal, SignalResult
from . import face_backend as fb
from .image_quality import measure

KEY, NAME = "face_match", "Face matching"

LIMITATIONS = [
    "A similarity score measures how alike two face images look to the model; it is not proof of identity.",
    "Accuracy drops with poor lighting, pose, occlusion, age gap and low resolution.",
    "Face recognition models can perform unevenly across demographic groups; the threshold is not validated for this population.",
    "Cannot detect a high-quality deepfake or a look-alike.",
]


def _pick_single_face(img: np.ndarray, label: str) -> tuple[Optional[fb.Face], list[str]]:
    faces = fb.detect(img)
    if not faces:
        return None, [f"No face detected in the {label}."]
    if len(faces) > 1:
        return None, [f"{len(faces)} faces detected in the {label}; exactly one is required."]
    f = faces[0]
    if f.size < settings.min_face_px:
        return None, [f"The face in the {label} is too small ({f.size}px, minimum {settings.min_face_px}px)."]
    return f, []


def compare(reference: np.ndarray, capture: np.ndarray, capture_label: str = "candidate capture") -> Signal:
    method = f"Detector: {fb.detector_name()}; embedding: OpenCV SFace cosine similarity"
    if not fb.embedding_available():
        return Signal.not_run(KEY, NAME,
                              "Face embedding model is not installed. Run `python scripts/download_models.py`. "
                              "No similarity was estimated — matching is never simulated.", method)

    q_ref, q_cap = measure(reference), measure(capture)
    metrics = {"reference_quality": q_ref.as_dict(), "capture_quality": q_cap.as_dict()}
    f_ref, issues_ref = _pick_single_face(reference, "reference photo")
    f_cap, issues_cap = _pick_single_face(capture, capture_label)
    issues = issues_ref + issues_cap
    if issues:
        return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence=issues, quality=Quality.POOR,
                      method=method, limitations=LIMITATIONS, metrics=metrics, recapture_recommended=True)

    quality_issues = [f"Reference: {i}" for i in q_ref.issues] + [f"Capture: {i}" for i in q_cap.issues]
    sim = fb.cosine(fb.embed(reference, f_ref), fb.embed(capture, f_cap))
    thr, margin = settings.face_match_threshold, settings.face_match_margin
    metrics.update(similarity=round(sim, 4), threshold=thr, margin=margin,
                   reference_face_px=f_ref.size, capture_face_px=f_cap.size,
                   reference_detector_score=f_ref.score, capture_detector_score=f_cap.score)
    evidence = [f"Cosine similarity {sim:.3f} (model's published same-person threshold {thr:.3f}; "
                f"uncertainty band ±{margin:.2f})."]
    quality = Quality.POOR if quality_issues else max(q_ref.quality, q_cap.quality, key=lambda q: list(Quality).index(q))

    if quality_issues and sim < thr + margin:
        evidence += quality_issues
        return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence=evidence + [
            "Image quality is too low to interpret a low similarity."], quality=Quality.POOR,
            method=method, limitations=LIMITATIONS, metrics=metrics, recapture_recommended=True)

    if sim >= thr + margin:
        return Signal(KEY, NAME, SignalResult.NO_CONCERN, evidence=evidence + quality_issues,
                      quality=quality, method=method, limitations=LIMITATIONS, metrics=metrics)
    if sim < thr - margin:
        sev = 1.0 if sim < thr - 3 * margin else 0.7
        return Signal(KEY, NAME, SignalResult.CONCERN, evidence=evidence + [
            "Similarity is clearly below the threshold: the two images may show different people."],
            quality=quality, method=method, limitations=LIMITATIONS, metrics=metrics, severity=sev,
            findings=[Finding("Embedding similarity", f"{sim:.3f} < {thr - margin:.3f}", "high" if sev == 1 else "medium",
                              "The faces look dissimilar to the model.",
                              "Does not prove impersonation; pose, lighting or age can lower similarity.")])
    return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence=evidence + [
        "Similarity is inside the uncertainty band around the threshold."], quality=quality,
        method=method, limitations=LIMITATIONS, metrics=metrics, recapture_recommended=True)
