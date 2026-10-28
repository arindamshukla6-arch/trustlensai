"""Random challenge-response check using two live snapshots.

The reviewer's screen issues an unpredictable instruction (chosen with the
`secrets` module). The candidate takes a baseline snapshot and then a second
snapshot after following the instruction. We measure whether the detected face
moved in the requested way, whether the two snapshots differ, and whether the
response arrived before the challenge expired.

This is a preliminary presentation-attack screening signal. A determined
attacker with a live deepfake or a cooperative accomplice can pass it.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from ..config import settings
from ..models import Finding, Quality, Signal, SignalResult
from . import face_backend as fb

KEY, NAME = "challenge_response", "Live challenge-response (preliminary)"

CHALLENGES = {
    "closer": "Move noticeably closer to the camera.",
    "farther": "Lean back so your face looks smaller in the frame.",
    "sideways": "Move your head clearly to one side of the frame (left or right).",
}

LIMITATIONS = [
    "Only checks that a detected face moved as instructed between two snapshots.",
    "Does not detect live deepfakes, masks or a cooperating impostor.",
    "Browser snapshots are not cryptographically bound to the device; the capture path can be tampered with.",
]


@dataclass
class Challenge:
    code: str
    instruction: str
    nonce: str
    issued_at: float

    def to_dict(self) -> dict:
        return asdict(self)


def issue() -> Challenge:
    code = secrets.choice(sorted(CHALLENGES))
    return Challenge(code, CHALLENGES[code], secrets.token_hex(8), time.time())


def evaluate(ch: Challenge, baseline: np.ndarray, response: np.ndarray, responded_at: float | None = None) -> Signal:
    method = f"Face box displacement between two snapshots ({fb.detector_name()}), random challenge, {settings.challenge_ttl_seconds}s expiry"
    responded_at = responded_at or time.time()
    elapsed = responded_at - ch.issued_at
    metrics = {"challenge": ch.code, "instruction": ch.instruction, "nonce": ch.nonce,
               "elapsed_s": round(elapsed, 1)}
    if fb.detector_name() == "none":
        return Signal.not_run(KEY, NAME, "No face detector available.", method)
    if elapsed > settings.challenge_ttl_seconds:
        return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence=[
            f"Response took {elapsed:.0f}s; the challenge expired after {settings.challenge_ttl_seconds}s. Issue a new challenge."],
            quality=Quality.UNKNOWN, method=method, limitations=LIMITATIONS, metrics=metrics,
            recapture_recommended=True)

    fa, fbx = fb.detect(baseline), fb.detect(response)
    if len(fa) != 1 or len(fbx) != 1:
        return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence=[
            f"Exactly one face is required in each snapshot (found {len(fa)} and {len(fbx)})."],
            quality=Quality.POOR, method=method, limitations=LIMITATIONS, metrics=metrics,
            recapture_recommended=True)

    a, b = fa[0], fbx[0]
    w = baseline.shape[1]
    ga = cv2.resize(cv2.cvtColor(baseline, cv2.COLOR_BGR2GRAY), (64, 64)).astype(np.float32)
    gb = cv2.resize(cv2.cvtColor(response, cv2.COLOR_BGR2GRAY), (64, 64)).astype(np.float32)
    image_diff = float(np.mean(np.abs(ga - gb)))
    area_ratio = (b.box[2] * b.box[3]) / max(1, a.box[2] * a.box[3])
    shift = abs(b.center[0] - a.center[0]) / w
    metrics.update(area_ratio=round(area_ratio, 3), horizontal_shift=round(shift, 3),
                   image_difference=round(image_diff, 2))

    passed = {"closer": area_ratio >= 1.25, "farther": area_ratio <= 0.8, "sideways": shift >= 0.12}[ch.code]
    findings = []
    if image_diff < 0.5:
        findings.append(Finding("Identical snapshots", f"Snapshots differ by only {image_diff:.2f}/255", "high",
                                "The same image may have been submitted twice (e.g. a static photo or virtual camera).",
                                "Does not prove an attack on its own."))
    evidence = [f"Challenge: “{ch.instruction}”", f"Face area ratio {area_ratio:.2f}, horizontal shift {shift:.0%} of frame width.",
                f"Response received after {elapsed:.0f}s."]
    if findings:
        return Signal(KEY, NAME, SignalResult.CONCERN, evidence + [findings[0].observation], Quality.ADEQUATE, method,
                      LIMITATIONS, severity=1.0, findings=findings, metrics=metrics)
    if passed:
        return Signal(KEY, NAME, SignalResult.NO_CONCERN, evidence + ["The face moved as instructed."],
                      Quality.ADEQUATE, method, LIMITATIONS, metrics=metrics)
    # Not following an instruction is usually a misunderstanding, so we ask for a retry.
    return Signal(KEY, NAME, SignalResult.INCONCLUSIVE, evidence + [
        "The requested movement was not detected. Ask the candidate to retry with a new challenge."],
        Quality.ADEQUATE, method, LIMITATIONS, metrics=metrics, recapture_recommended=True)
