"""Preliminary presentation-attack (replay) screening for uploaded videos.

What is actually computed:
* Frames are sampled with OpenCV (up to MAX_VIDEO_FRAMES, evenly spaced).
* Each frame is reduced to a 64x64 greyscale thumbnail.
* Frozen segments: consecutive sampled frames whose mean absolute difference
  (MAD) is below FROZEN_FRAME_DIFF. A live camera always has sensor noise and
  micro-motion, so long perfectly-still stretches are unusual.
* Loops: a run of >= LOOP_MIN_RUN consecutive frames that reappear almost
  pixel-identical later in the video, AFTER the scene had visibly changed in
  between. This is the signature of a clip being played back repeatedly.
* Face presence per frame, brightness and sharpness.

This is NOT full liveness detection and cannot detect deepfakes, high-quality
screen replays, masks, or injected camera streams.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from ..config import settings
from ..models import Finding, Quality, Signal, SignalResult
from . import face_backend as fb

KEY, NAME = "video_replay", "Replay / presentation-attack screening (preliminary)"

LIMITATIONS = [
    "Preliminary screening only: frame-similarity and frozen-frame checks cannot prove a video is live or genuine.",
    "Does not detect deepfakes, face-swaps, masks, high-quality screen replays or virtual-camera injection.",
    "A candidate sitting very still under a noise-free camera can produce frozen-frame indicators.",
    "Heavy compression can make distinct frames look identical.",
]


@dataclass
class FrameStats:
    index: int
    t: float
    thumb: np.ndarray
    brightness: float
    sharpness: float
    faces: int


def _thumb(gray: np.ndarray) -> np.ndarray:
    return cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)


def _mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def read_frames(path: Path, progress: Optional[Callable[[float], None]] = None):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("OpenCV could not open this video (unsupported codec or corrupt file).")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0 or fps > 240:
            fps = 25.0
        stride = max(1, total // settings.max_video_frames) if total > 0 else 1
        frames, best, best_sharp, idx = [], None, -1.0, 0
        face_every = max(1, (total // stride) // 60) if total else 3
        sampled = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0 and len(frames) < settings.max_video_frames:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                faces = -1
                if sampled % face_every == 0:
                    found = fb.detect(frame)
                    faces = len(found)
                    if faces == 1 and sharp > best_sharp:
                        best, best_sharp = frame.copy(), sharp
                frames.append(FrameStats(idx, idx / fps, _thumb(gray), float(gray.mean()), sharp, faces))
                sampled += 1
                if progress and total:
                    progress(min(1.0, idx / total))
            idx += 1
        return frames, fps, idx, best
    finally:
        cap.release()


def find_frozen_runs(frames: list[FrameStats]) -> list[tuple[float, float]]:
    runs, start = [], None
    for a, b in zip(frames, frames[1:]):
        if _mad(a.thumb, b.thumb) < settings.frozen_diff:
            start = a if start is None else start
            end = b
        elif start is not None:
            runs.append((start.t, end.t))
            start = None
    if start is not None:
        runs.append((start.t, end.t))
    return [r for r in runs if r[1] - r[0] >= settings.frozen_run_seconds]


def find_loops(frames: list[FrameStats], fps_sampled: float) -> list[dict]:
    """Find runs of frames that repeat later after the scene changed in between."""
    n = len(frames)
    if n < 2 * settings.loop_min_run:
        return []
    thumbs = np.stack([f.thumb for f in frames])
    min_gap = max(settings.loop_min_run, int(settings.loop_min_gap_seconds * fps_sampled))
    loops, used = [], set()
    for i in range(n - settings.loop_min_run):
        if i in used:
            continue
        for j in range(i + min_gap, n - settings.loop_min_run + 1):
            if _mad(thumbs[i], thumbs[j]) >= settings.loop_match_diff:
                continue
            run = 0
            while j + run < n and i + run < j and _mad(thumbs[i + run], thumbs[j + run]) < settings.loop_match_diff:
                run += 1
            if run < settings.loop_min_run:
                continue
            between = np.mean(np.abs(thumbs[i:j] - thumbs[i]), axis=(1, 2))
            if between.max() < settings.loop_motion_diff:
                continue  # scene never changed: this is stillness, not a loop
            loops.append({"first_start": round(frames[i].t, 2), "first_end": round(frames[i + run - 1].t, 2),
                          "repeat_start": round(frames[j].t, 2), "repeat_end": round(frames[j + run - 1].t, 2),
                          "frames": run})
            used.update(range(i, i + run))
            break
        if len(loops) >= 5:
            break
    return loops


def analyse(path: Path, progress: Optional[Callable[[float], None]] = None) -> tuple[Signal, Optional[np.ndarray]]:
    method = (f"OpenCV frame sampling, 64x64 frame differencing, loop search; face detector: {fb.detector_name()}")
    frames, fps, total, best = read_frames(path, progress)
    if len(frames) < 10:
        return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence=[
            f"Only {len(frames)} frames could be read; at least 10 are needed."],
            quality=Quality.POOR, method=method, limitations=LIMITATIONS,
            metrics={"frames_read": total}, recapture_recommended=True), best

    duration = total / fps
    sampled_fps = len(frames) / max(duration, 1e-6)
    checked = [f for f in frames if f.faces >= 0]
    one_face = sum(1 for f in checked if f.faces == 1)
    multi = [round(f.t, 2) for f in checked if f.faces > 1]
    no_face = [round(f.t, 2) for f in checked if f.faces == 0]
    brightness = float(np.mean([f.brightness for f in frames]))
    sharpness = float(np.median([f.sharpness for f in frames]))
    h, w = frames[0].thumb.shape
    diffs = [_mad(a.thumb, b.thumb) for a, b in zip(frames, frames[1:])]

    metrics = {
        "frames_total": total, "frames_sampled": len(frames), "fps": round(fps, 2),
        "duration_s": round(duration, 2), "mean_brightness": round(brightness, 1),
        "median_sharpness": round(sharpness, 1), "face_checked_frames": len(checked),
        "single_face_frames": one_face, "multi_face_timestamps": multi[:20],
        "no_face_timestamps": no_face[:20], "detector": fb.detector_name(),
        "frame_diff_series": [round(d, 3) for d in diffs], "frame_times": [round(f.t, 2) for f in frames[1:]],
    }

    quality_issues = []
    if duration < settings.min_video_seconds:
        quality_issues.append(f"Video is only {duration:.1f}s long (minimum {settings.min_video_seconds:.0f}s).")
    if brightness < settings.min_brightness:
        quality_issues.append(f"Video is too dark (mean brightness {brightness:.0f}/255).")
    if brightness > settings.max_brightness:
        quality_issues.append(f"Video is over-exposed (mean brightness {brightness:.0f}/255).")
    if sharpness < settings.min_sharpness:
        quality_issues.append(f"Video is blurry (median sharpness {sharpness:.0f}).")
    face_ratio = one_face / len(checked) if checked else 0.0
    detector_ok = fb.detector_name() != "none"
    if detector_ok and face_ratio < 0.5:
        quality_issues.append("Too few frames show exactly one face to confirm the candidate was on camera.")

    findings: list[Finding] = []
    frozen = find_frozen_runs(frames)
    loops = find_loops(frames, sampled_fps)
    for a, b in frozen:
        findings.append(Finding("Frozen frames", f"No measurable change between {a:.1f}s and {b:.1f}s",
                                "medium", "Can indicate a still image or paused playback presented to the camera.",
                                "Does not prove an attack; a very still person and a noise-free camera can cause this.",
                                f"{a:.1f}s–{b:.1f}s"))
    for lp in loops:
        findings.append(Finding("Repeated segment",
                                f"Frames {lp['first_start']}s–{lp['first_end']}s reappear at {lp['repeat_start']}s–{lp['repeat_end']}s "
                                f"({lp['frames']} sampled frames) after the scene changed in between",
                                "high", "Consistent with a recorded clip being replayed in a loop.",
                                "Does not prove an attack; repetitive scenes and some encoders can produce near-identical frames.",
                                f"{lp['repeat_start']}s"))
    if multi:
        findings.append(Finding("Multiple faces", f"More than one face at {', '.join(map(str, multi[:5]))}s", "low",
                                "Another person may be present.", "Posters, photos or reflections also count as faces.",
                                f"{multi[0]}s"))
    metrics["frozen_runs"] = frozen
    metrics["loops"] = loops

    evidence = [f"Analysed {len(frames)} of {total} frames over {duration:.1f}s at {fps:.0f} fps.",
                f"Single face visible in {face_ratio:.0%} of {len(checked)} checked frames ({fb.detector_name()})."
                if detector_ok else "No face detector available; face presence not checked."]
    if not findings:
        evidence.append("No frozen stretches or repeated segments were found.")
    else:
        evidence += [f.observation for f in findings]

    quality = Quality.POOR if quality_issues else (Quality.GOOD if sharpness > 2 * settings.min_sharpness else Quality.ADEQUATE)
    severity = max((f.value for f in findings), default=0.0)

    if severity >= 0.6:
        result = SignalResult.CONCERN
    elif quality_issues:
        result = SignalResult.INCONCLUSIVE
    else:
        result = SignalResult.NO_CONCERN
    evidence += quality_issues
    return Signal(KEY, NAME, result, evidence=evidence, quality=quality, method=method,
                  limitations=LIMITATIONS, severity=severity if result is SignalResult.CONCERN else 0.0,
                  findings=findings, metrics=metrics, recapture_recommended=bool(quality_issues)), best
