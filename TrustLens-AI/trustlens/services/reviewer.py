"""Human review actions. This is the ONLY code path that sets a decision."""
from __future__ import annotations

from .. import database as db
from ..models import HUMAN_DECISIONS, CaseStatus
from ..security import valid_reviewer_id


class ReviewError(ValueError):
    pass


def record_decision(case_id: str, reviewer_id: str, decision: CaseStatus, notes: str,
                    authorised: bool) -> dict:
    """Record an explicit human decision.

    Requires: an authorised session, a valid reviewer ID, a decision from the
    allowed human set, a completed analysis, and written notes.
    """
    if not authorised:
        raise ReviewError("Only an authorised reviewer can record a decision.")
    if not valid_reviewer_id(reviewer_id):
        raise ReviewError("Enter a valid reviewer ID (2–40 letters, digits, . _ -).")
    if not isinstance(decision, CaseStatus) or decision not in HUMAN_DECISIONS:
        raise ReviewError("Decision must be one of the human review outcomes.")
    notes = (notes or "").strip()
    if len(notes) < 10:
        raise ReviewError("Write at least a short reason (10+ characters) for the decision.")
    case = db.get_case(case_id)
    if not case:
        raise ReviewError("Case not found.")
    if case["status"] == CaseStatus.DRAFT.value:
        raise ReviewError("Run the checks before recording a decision.")
    with db.connect() as c:
        ts = db.now()
        c.execute("INSERT INTO decisions (case_id, reviewer_id, decision, notes, created_at) VALUES (?,?,?,?,?)",
                  (case_id, reviewer_id, decision.value, notes[:4000], ts))
        db._set_status_by_human(c, case_id, decision)
        db.add_audit(case_id, reviewer_id, "human_decision_recorded",
                     {"decision": decision.value, "previous_status": case["status"],
                      "risk_band_at_decision": case["risk_band"]}, conn=c)
    return {"case_id": case_id, "decision": decision.value, "reviewer_id": reviewer_id, "created_at": ts}


def record_appeal(case_id: str, recorded_by: str, reason: str, authorised: bool) -> None:
    if not authorised:
        raise ReviewError("Only an authorised reviewer can record an appeal.")
    if not valid_reviewer_id(recorded_by):
        raise ReviewError("Enter a valid reviewer ID.")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ReviewError("Describe the candidate's dispute (10+ characters).")
    if not db.get_case(case_id):
        raise ReviewError("Case not found.")
    with db.connect() as c:
        c.execute("INSERT INTO appeals (case_id, recorded_by, reason, created_at) VALUES (?,?,?,?)",
                  (case_id, recorded_by, reason[:4000], db.now()))
        c.execute("UPDATE cases SET disputed=1, updated_at=? WHERE case_id=?", (db.now(), case_id))
        db.add_audit(case_id, recorded_by, "case_disputed", {"appeal_recorded": True}, conn=c)
