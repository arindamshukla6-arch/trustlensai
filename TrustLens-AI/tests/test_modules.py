from pathlib import Path

import numpy as np

from trustlens.models import SignalResult
from trustlens.modules import document_forensics, face_backend, face_matching, text_analysis, video_analysis, challenge
from trustlens.services.sample_data import AI_STYLED_SOP, HUMAN_SOP


def test_genuine_pdf_has_no_concern(samples, tmp_path):
    sigs = {s.key: s for s in document_forensics.analyse(samples["genuine_certificate"], tmp_path)}
    assert sigs["doc_integrity"].result is SignalResult.NO_CONCERN
    assert sigs["doc_metadata"].result is SignalResult.NO_CONCERN


def test_tampered_pdf_is_flagged_with_explained_findings(samples, tmp_path):
    sigs = {s.key: s for s in document_forensics.analyse(samples["tampered_certificate"], tmp_path)}
    integ = sigs["doc_integrity"]
    assert integ.result is SignalResult.CONCERN
    checks = {f.check for f in integ.findings}
    assert {"Incremental updates", "Covering shapes"} <= checks
    assert all(f.does_not_mean for f in integ.findings)
    assert sigs["doc_metadata"].result is SignalResult.CONCERN  # modified before created


def test_corrupt_pdf_fails_safely(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.4 garbage")
    sigs = document_forensics.analyse(p, tmp_path)
    assert all(s.result is SignalResult.ERROR for s in sigs)


def test_edited_scan_flagged_genuine_not(samples, tmp_path):
    good = document_forensics.analyse(samples["genuine_scan"], tmp_path)[0]
    bad = document_forensics.analyse(samples["tampered_scan"], tmp_path)[0]
    assert good.result is SignalResult.NO_CONCERN
    assert bad.result is SignalResult.CONCERN
    x0, y0, x1, y1 = bad.metrics["ela_region"]
    assert x0 <= 450 and x1 >= 680 and 400 <= y0 <= 480  # the pasted grade region


def test_replay_loop_detected(samples):
    s, _ = video_analysis.analyse(samples["replay_video"])
    assert s.result is SignalResult.CONCERN
    assert s.metrics["loops"]
    assert any(f.check == "Repeated segment" for f in s.findings)


def test_continuous_motion_has_no_loop(samples):
    s, _ = video_analysis.analyse(samples["motion_video"])
    assert not s.metrics["loops"] and not s.metrics["frozen_runs"]
    assert s.result is not SignalResult.CONCERN


def test_poor_video_is_inconclusive_with_recapture(samples):
    s, _ = video_analysis.analyse(samples["poor_video"])
    assert s.result is SignalResult.INCONCLUSIVE
    assert s.recapture_recommended


def test_unreadable_video_raises(tmp_path):
    p = tmp_path / "x.mp4"
    p.write_bytes(b"\x00" * 100)
    try:
        video_analysis.analyse(p)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_text_indicator_is_weak_and_needs_length():
    assert text_analysis.analyse("Too short.").result is SignalResult.INCONCLUSIVE
    generic = text_analysis.analyse(AI_STYLED_SOP)
    specific = text_analysis.analyse(HUMAN_SOP)
    assert generic.result is SignalResult.CONCERN and generic.severity <= 0.5
    assert specific.result is SignalResult.NO_CONCERN
    assert any("never" in e.lower() for e in generic.evidence)


def test_face_matching_never_simulated_without_model(monkeypatch):
    monkeypatch.setattr(face_backend, "embedding_available", lambda: False)
    img = np.full((480, 640, 3), 128, np.uint8)
    s = face_matching.compare(img, img)
    assert s.result is SignalResult.NOT_RUN
    assert "similarity" not in s.metrics


def test_face_matching_no_face_is_inconclusive(monkeypatch):
    monkeypatch.setattr(face_backend, "embedding_available", lambda: True)
    monkeypatch.setattr(face_backend, "detect", lambda img: [])
    img = np.full((480, 640, 3), 128, np.uint8)
    s = face_matching.compare(img, img)
    assert s.result is SignalResult.INCONCLUSIVE and s.recapture_recommended


def test_face_matching_multiple_faces_is_inconclusive(monkeypatch):
    monkeypatch.setattr(face_backend, "embedding_available", lambda: True)
    two = [face_backend.Face((10, 10, 100, 100), 0.9), face_backend.Face((200, 10, 100, 100), 0.9)]
    monkeypatch.setattr(face_backend, "detect", lambda img: two)
    img = np.full((480, 640, 3), 128, np.uint8)
    assert face_matching.compare(img, img).result is SignalResult.INCONCLUSIVE


def test_challenge_expiry_and_identical_snapshots(monkeypatch):
    ch = challenge.issue()
    assert ch.code in challenge.CHALLENGES and len(ch.nonce) == 16
    img = np.full((480, 640, 3), 100, np.uint8)
    expired = challenge.Challenge(ch.code, ch.instruction, ch.nonce, ch.issued_at - 10_000)
    assert challenge.evaluate(expired, img, img).result is SignalResult.INCONCLUSIVE
    face = face_backend.Face((200, 150, 150, 150), 0.9)
    monkeypatch.setattr(face_backend, "detect", lambda im: [face])
    monkeypatch.setattr(face_backend, "detector_name", lambda: "test")
    s = challenge.evaluate(ch, img, img.copy())
    assert s.result is SignalResult.CONCERN  # identical snapshots
