from trustlens.config import settings
from trustlens.models import Quality, RiskBand, Signal, SignalResult
from trustlens.scoring import assess


def sig(key, result, severity=1.0, **kw):
    return Signal(key=key, name=key, result=result, severity=severity, **kw)


def test_no_signals_is_inconclusive():
    assert assess([]).band is RiskBand.INCONCLUSIVE


def test_missing_signals_are_not_suspicious():
    a = assess([sig("doc_integrity", SignalResult.NO_CONCERN),
                Signal.not_run("face_match", "Face", "no photo"),
                Signal.not_run("video_replay", "Video", "no video")])
    assert a.band is RiskBand.LOW
    assert a.score == 0


def test_errors_and_inconclusive_add_nothing():
    a = assess([sig("doc_integrity", SignalResult.NO_CONCERN),
                Signal.failed("video_replay", "Video", "boom"),
                sig("face_match", SignalResult.INCONCLUSIVE)])
    assert a.score == 0 and a.band is RiskBand.LOW
    assert a.recapture_recommended  # a core check was inconclusive


def test_only_inconclusive_core_checks_give_inconclusive_band():
    a = assess([sig("video_replay", SignalResult.INCONCLUSIVE, recapture_recommended=True)])
    assert a.band is RiskBand.INCONCLUSIVE
    assert a.recapture_recommended
    assert any("recapture" in s.lower() for s in a.next_steps)


def test_weights_and_thresholds():
    a = assess([sig("doc_integrity", SignalResult.CONCERN, 1.0)])
    assert a.score == settings.weights["doc_integrity"]
    assert a.band is RiskBand.MODERATE
    b = assess([sig("doc_integrity", SignalResult.CONCERN, 1.0), sig("video_replay", SignalResult.CONCERN, 1.0)])
    assert b.band is RiskBand.ELEVATED


def test_weak_ai_text_signal_cannot_raise_band_alone(monkeypatch):
    monkeypatch.setitem(settings.weights, "ai_text", 5.0)  # even with an absurd weight
    a = assess([sig("doc_integrity", SignalResult.NO_CONCERN), sig("ai_text", SignalResult.CONCERN, 1.0)])
    assert a.contributions["ai_text"] <= settings.weak_signal_cap
    assert a.band is RiskBand.LOW


def test_assessment_has_no_status_field():
    a = assess([sig("doc_integrity", SignalResult.CONCERN)])
    assert not hasattr(a, "status")
    assert "status" not in a.to_dict()
    assert "not" in a.disclaimer.lower() and "probability" in a.disclaimer.lower()


def test_scoring_module_cannot_touch_database():
    import trustlens.scoring as scoring
    assert not hasattr(scoring, "db") and not hasattr(scoring, "database")
