"""Runs the checks for a case. It never sets a final decision."""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import Callable, Optional

from . import audit
from . import database as db
from .models import RiskAssessment, Signal
from .modules import document_forensics, face_matching, text_analysis, video_analysis
from .modules.image_quality import read_image
from .scoring import assess
from .security import case_dir

Progress = Callable[[str, float], None]


def _latest(files: list[dict], kind: str) -> Optional[Path]:
    match = [f for f in files if f["kind"] == kind]
    return Path(match[-1]["stored_path"]) if match else None


def _safe(fn, key: str, name: str):
    try:
        return fn()
    except Exception as e:  # every check fails safely into an ERROR signal
        traceback.print_exc()
        return Signal.failed(key, name, f"{type(e).__name__}: {e}")


def run_case(case_id: str, actor: str, progress: Optional[Progress] = None,
             extra_signals: Optional[list[Signal]] = None,
             statement_text: Optional[str] = None) -> tuple[list[Signal], RiskAssessment]:
    report = progress or (lambda msg, frac: None)
    files = db.get_files(case_id)
    work = case_dir(case_id)
    signals: list[Signal] = []
    audit.log("analysis_started", actor, case_id)

    ref, cap_img, cap_vid = _latest(files, "reference_image"), _latest(files, "capture_image"), _latest(files, "capture_video")
    doc, stmt = _latest(files, "document"), _latest(files, "statement")

    # 1. Video replay screening
    best_frame = None
    if cap_vid:
        report("Screening video for replay indicators…", 0.10)
        def _video():
            nonlocal best_frame
            s, best_frame = video_analysis.analyse(cap_vid, lambda f: report("Reading video frames…", 0.10 + 0.3 * f))
            return s
        signals.append(_safe(_video, video_analysis.KEY, video_analysis.NAME))
    else:
        reason = ("A still image cannot show liveness. Upload a short video or use the live challenge."
                  if cap_img else "No capture video uploaded.")
        signals.append(Signal.not_run(video_analysis.KEY, video_analysis.NAME, reason))

    # 2. Face matching
    report("Comparing faces…", 0.45)
    if ref and (cap_img or best_frame is not None):
        def _face():
            capture = read_image(cap_img) if cap_img else best_frame
            label = "candidate photo" if cap_img else "sharpest video frame"
            return face_matching.compare(read_image(ref), capture, label)
        signals.append(_safe(_face, face_matching.KEY, face_matching.NAME))
    else:
        missing = "reference photo" if not ref else "candidate capture with a detectable face"
        signals.append(Signal.not_run(face_matching.KEY, face_matching.NAME, f"No {missing} available."))

    # 3. Document forensics
    report("Inspecting document…", 0.65)
    if doc:
        try:
            signals.extend(document_forensics.analyse(doc, work))
        except Exception as e:
            signals.append(Signal.failed("doc_integrity", "Document structure integrity", str(e)))
    else:
        signals.append(Signal.not_run("doc_integrity", "Document structure integrity", "No document uploaded."))

    # 4. Statement style (weak)
    report("Checking statement style (weak signal)…", 0.85)
    text = statement_text
    if text is None and stmt:
        text = _safe(lambda: document_forensics.extract_text(stmt), text_analysis.KEY, text_analysis.NAME)
    if isinstance(text, Signal):
        signals.append(text)
    elif text and text.strip():
        signals.append(_safe(lambda: text_analysis.analyse(text), text_analysis.KEY, text_analysis.NAME))
    else:
        signals.append(Signal.not_run(text_analysis.KEY, text_analysis.NAME, "No statement provided."))

    for s in extra_signals or []:
        signals = [x for x in signals if x.key != s.key] + [s]

    report("Aggregating signals…", 0.95)
    assessment = assess(signals)
    db.save_analysis(case_id, signals, assessment)
    audit.log("analysis_completed", actor, case_id, risk_band=assessment.band.value,
              score=assessment.score, signals={s.key: s.result.value for s in signals})
    report("Done", 1.0)
    return signals, assessment


def rescore_with(case_id: str, actor: str, new_signal: Signal) -> RiskAssessment:
    """Add or replace one signal (e.g. a live challenge) and re-aggregate."""
    signals = [s for s in db.get_signals(case_id) if s.key != new_signal.key] + [new_signal]
    assessment = assess(signals)
    db.save_analysis(case_id, signals, assessment)
    audit.log("signal_added", actor, case_id, signal=new_signal.key, result=new_signal.result.value,
              risk_band=assessment.band.value)
    return assessment
