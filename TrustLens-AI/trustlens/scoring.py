"""Transparent, rule-based aggregation of signals into an ADVISORY risk band.

Rules (documented so a reviewer can reproduce any result by hand):

1. Only signals whose result is NO_CONCERN or CONCERN are "completed".
   NOT_RUN, ERROR and INCONCLUSIVE signals are never treated as suspicious;
   they add nothing to the score.
2. If no critical (core) signal completed, the band is INCONCLUSIVE.
3. score = sum(weight[key] * severity) over CONCERN signals.
   Weak signals (the AI-text indicator) contribute at most WEAK_SIGNAL_CAP in
   total, which is below the Moderate threshold, so they can never raise a case
   above Low by themselves.
4. score >= elevated_threshold -> ELEVATED; >= moderate_threshold -> MODERATE;
   otherwise LOW.
5. If a core check was inconclusive because of poor input quality, a recapture
   is recommended and the reasons say the evidence is partial.

This module deliberately has no access to the database. A risk band is
advisory; it cannot set or change a candidate's status.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .config import Settings, settings as default_settings
from .models import RiskAssessment, RiskBand, Signal, SignalResult

DISCLAIMER = (
    "This risk band is an advisory triage aid produced by unvalidated, rule-based "
    "aggregation. It is NOT a probability that the candidate committed fraud, and any "
    "model confidence or similarity shown describes a measurement, not guilt. "
    "Only an authorised human reviewer may record a decision."
)


def assess(signals: Iterable[Signal], cfg: Optional[Settings] = None) -> RiskAssessment:
    cfg = cfg or default_settings
    signals = list(signals)
    completed = [s for s in signals if s.result.completed]
    incomplete = [s for s in signals if not s.result.completed]
    reasons: list[str] = []
    contributions: dict[str, float] = {}

    weak_total = 0.0
    score = 0.0
    for s in completed:
        if s.result is not SignalResult.CONCERN:
            continue
        w = cfg.weights.get(s.key, 0.0)
        sev = max(0.0, min(1.0, s.severity if s.severity > 0 else 1.0))
        c = w * sev
        if s.key in cfg.weak_signals:
            allowed = max(0.0, cfg.weak_signal_cap - weak_total)
            c = min(c, allowed)
            weak_total += c
        contributions[s.key] = round(c, 4)
        score += c
        reasons.append(f"{s.name}: indicator found (weight {w:.2f} x severity {sev:.2f} = {c:.3f}).")

    core_completed = [s for s in completed if s.key in cfg.critical_signals]
    core_poor = [s for s in signals if s.key in cfg.critical_signals
                 and s.result is SignalResult.INCONCLUSIVE]
    recapture = any(s.recapture_recommended for s in signals) or bool(core_poor)

    for s in incomplete:
        label = {"not_run": "not run", "error": "could not be completed",
                 "inconclusive": "inconclusive"}[s.result.value]
        reasons.append(f"{s.name}: {label} — not counted as suspicious.")

    if not core_completed:
        band = RiskBand.INCONCLUSIVE
        reasons.insert(0, "No core check produced a usable result, so no risk band can be given.")
    elif score >= cfg.elevated_threshold:
        band = RiskBand.ELEVATED
    elif score >= cfg.moderate_threshold:
        band = RiskBand.MODERATE
    else:
        band = RiskBand.LOW

    if core_poor and band is not RiskBand.INCONCLUSIVE:
        reasons.append("Evidence is partial: at least one core check was inconclusive.")
    if not any(s.result is SignalResult.CONCERN for s in completed) and band is RiskBand.LOW:
        reasons.insert(0, "No completed check produced an indicator.")

    return RiskAssessment(
        band=band,
        score=round(score, 4),
        reasons=reasons,
        contributions=contributions,
        completed_signals=[s.key for s in completed],
        incomplete_signals=[s.key for s in incomplete],
        recapture_recommended=recapture,
        next_steps=next_steps(band, signals, recapture),
        disclaimer=DISCLAIMER,
    )


def next_steps(band: RiskBand, signals: list[Signal], recapture: bool) -> list[str]:
    steps: list[str] = []
    by_key = {s.key: s for s in signals}
    if recapture:
        steps.append("Request a recapture in good, even lighting with the face clearly visible.")
    if band is RiskBand.INCONCLUSIVE:
        steps.append("Do not draw conclusions. Collect usable inputs and re-run the checks.")
    if (s := by_key.get("face_match")) and s.result is SignalResult.CONCERN:
        steps.append("Compare the reference photo and capture side by side; arrange a live video call if doubt remains.")
    if (s := by_key.get("video_replay")) and s.result is SignalResult.CONCERN:
        steps.append("Review the flagged frame timestamps; ask for a fresh live session with a challenge-response.")
    if (s := by_key.get("challenge_response")) and s.result is SignalResult.CONCERN:
        steps.append("Repeat the challenge-response under supervision.")
    if any((s := by_key.get(k)) and s.result is SignalResult.CONCERN
           for k in ("doc_integrity", "doc_metadata", "image_forensics")):
        steps.append("Contact the issuing institution through an official channel to confirm the document.")
    if (s := by_key.get("ai_text")) and s.result is SignalResult.CONCERN:
        steps.append("Treat the AI-text indicator as weak. If relevant, discuss the statement with the candidate; never act on it alone.")
    if band in (RiskBand.LOW,) and not recapture:
        steps.append("Review the evidence briefly and record a decision.")
    steps.append("Record your decision and reasons in the reviewer panel. The candidate may dispute any decision.")
    return steps
