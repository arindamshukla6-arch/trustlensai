import pytest

from trustlens import database as db
from trustlens.models import CaseStatus, RiskBand, Signal, SignalResult
from trustlens.scoring import assess
from trustlens.services import reviewer


def _case(cid="TL-00000000AA"):
    db.create_case(cid, "CAND-1", "SESS-1", "tester")
    return cid


def _max_risk_signals():
    return [Signal(k, k, SignalResult.CONCERN, severity=1.0) for k in
            ("face_match", "video_replay", "challenge_response", "doc_integrity", "doc_metadata", "image_forensics", "ai_text")]


def test_automated_score_cannot_reject_candidate():
    cid = _case()
    signals = _max_risk_signals()
    a = assess(signals)
    assert a.band is RiskBand.ELEVATED
    db.save_analysis(cid, signals, a)
    case = db.get_case(cid)
    assert case["status"] == CaseStatus.AWAITING_REVIEW.value
    assert case["status"] not in (CaseStatus.CONFIRMED_CONCERN.value, "rejected")
    assert db.get_decisions(cid) == []


def test_no_rejected_status_exists():
    assert "rejected" not in {s.value for s in CaseStatus}


def test_reanalysis_never_overwrites_human_decision():
    cid = _case()
    db.save_analysis(cid, [], assess([]))
    reviewer.record_decision(cid, "rev.a", CaseStatus.VERIFIED, "Checked with issuer by phone.", authorised=True)
    signals = _max_risk_signals()
    db.save_analysis(cid, signals, assess(signals))
    assert db.get_case(cid)["status"] == CaseStatus.VERIFIED.value


def test_decision_requires_authorisation_and_reviewer():
    cid = _case()
    db.save_analysis(cid, [], assess([]))
    with pytest.raises(reviewer.ReviewError):
        reviewer.record_decision(cid, "rev.a", CaseStatus.VERIFIED, "Looks fine to me.", authorised=False)
    with pytest.raises(reviewer.ReviewError):
        reviewer.record_decision(cid, "", CaseStatus.VERIFIED, "Looks fine to me.", authorised=True)
    with pytest.raises(reviewer.ReviewError):
        reviewer.record_decision(cid, "rev.a", CaseStatus.VERIFIED, "ok", authorised=True)
    with pytest.raises(reviewer.ReviewError):
        reviewer.record_decision(cid, "rev.a", CaseStatus.AWAITING_REVIEW, "Not a decision value.", authorised=True)
    assert db.get_case(cid)["status"] == CaseStatus.AWAITING_REVIEW.value


def test_decision_must_follow_analysis():
    cid = _case()
    with pytest.raises(reviewer.ReviewError):
        reviewer.record_decision(cid, "rev.a", CaseStatus.VERIFIED, "Before analysis.", authorised=True)


def test_human_decision_is_recorded_and_audited():
    cid = _case()
    db.save_analysis(cid, [], assess([]))
    reviewer.record_decision(cid, "rev.b", CaseStatus.CONFIRMED_CONCERN, "Issuer confirmed no such certificate.", authorised=True)
    assert db.get_case(cid)["status"] == CaseStatus.CONFIRMED_CONCERN.value
    d = db.get_decisions(cid)[0]
    assert d["reviewer_id"] == "rev.b" and d["created_at"]
    assert any(e["event"] == "human_decision_recorded" and e["actor"] == "rev.b" for e in db.get_audit(cid))


def test_appeal_marks_case_disputed():
    cid = _case()
    reviewer.record_appeal(cid, "rev.c", "Candidate says the photo is old.", authorised=True)
    assert db.get_case(cid)["disputed"] == 1
    assert len(db.get_appeals(cid)) == 1
