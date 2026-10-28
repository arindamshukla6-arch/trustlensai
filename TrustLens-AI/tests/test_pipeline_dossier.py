import json

from trustlens import database as db
from trustlens.models import CaseStatus, RiskBand
from trustlens.security import UploadError, mask, safe_ext, store_upload
from trustlens.services import demo, dossier, retention, reviewer
from trustlens.services import sample_data


def _demo(key, monkeypatch, samples):
    monkeypatch.setattr(sample_data, "generate_all", lambda *a, **k: samples)
    return demo.create_demo_case(key, "tester")


def test_demo_scenarios_produce_expected_bands(monkeypatch, samples):
    expected = {"clean": RiskBand.LOW, "tampered_pdf": RiskBand.MODERATE,
                "replay_plus_doc": RiskBand.ELEVATED, "poor_quality": RiskBand.INCONCLUSIVE,
                "generic_statement": RiskBand.LOW, "edited_scan": RiskBand.MODERATE}
    for key, band in expected.items():
        cid = _demo(key, monkeypatch, samples)
        case = db.get_case(cid)
        assert case["risk_band"] == band.value, key
        assert case["is_demo"] == 1
        assert case["status"] == CaseStatus.AWAITING_REVIEW.value


def test_dossier_json_and_pdf(monkeypatch, samples):
    cid = _demo("replay_plus_doc", monkeypatch, samples)
    reviewer.record_decision(cid, "rev.d", CaseStatus.FURTHER_REVIEW, "Requested a supervised live session.", authorised=True)
    d = dossier.build(cid)
    assert d["demonstration"] is True and "synthetic" in d["demonstration_note"].lower()
    assert d["case"]["case_id"] == cid and d["advisory_risk"]["band"] == "Elevated"
    assert d["checks_not_completed"]  # face match not run
    assert "not the probability" in d["confidence_note"].lower()
    assert d["human_decisions"][0]["reviewer_id"] == "rev.d"
    parsed = json.loads(dossier.to_json(d))
    assert all("artifacts" not in s for s in parsed["signals"])  # no server paths exported
    pdf = dossier.to_pdf(d)
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000


def test_masked_dossier_hides_candidate_id(monkeypatch, samples):
    cid = _demo("clean", monkeypatch, samples)
    d = dossier.build(cid, include_private=False)
    assert d["case"]["candidate_id"] != "DEMO-CLEAN"


def test_delete_case_removes_files_and_rows(monkeypatch, samples):
    from trustlens.config import settings
    cid = _demo("clean", monkeypatch, samples)
    folder = settings.cases_dir / cid
    assert folder.exists()
    assert retention.delete_case(cid, "tester")
    assert not folder.exists() and db.get_case(cid) is None
    assert db.get_signals(cid) == [] and db.get_files(cid) == []
    assert any(e["event"] == "case_deleted" for e in db.get_audit(cid))


def test_upload_validation(tmp_path):
    db.create_case("TL-00000000BB", "C", "S", "t")
    try:
        store_upload("TL-00000000BB", "document", "evil.exe", b"MZ....")
        raise AssertionError
    except UploadError:
        pass
    try:  # extension says pdf, content is not
        store_upload("TL-00000000BB", "document", "fake.pdf", b"not a pdf")
        raise AssertionError
    except UploadError:
        pass
    try:
        store_upload("../../etc", "document", "a.pdf", b"%PDF-1.4")
        raise AssertionError
    except UploadError:
        pass
    sf = store_upload("TL-00000000BB", "document", "..\\..\\x.PDF", b"%PDF-1.4\n%%EOF")
    assert sf.path.name.startswith("document_") and sf.ext == ".pdf"
    assert safe_ext("../../a.tar.gz") == ".gz"
    assert mask("CAND-12345").startswith("CA") and "12345" not in mask("CAND-12345")
