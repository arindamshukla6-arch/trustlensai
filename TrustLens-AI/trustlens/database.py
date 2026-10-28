"""SQLite persistence. One connection per call keeps Streamlit reruns safe."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from .config import settings
from .models import CaseStatus, RiskAssessment, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id        TEXT PRIMARY KEY,
    candidate_ref  TEXT NOT NULL,
    session_id     TEXT NOT NULL,
    is_demo        INTEGER NOT NULL DEFAULT 0,
    demo_scenario  TEXT,
    status         TEXT NOT NULL,
    risk_band      TEXT,
    risk_score     REAL,
    assessment     TEXT,
    disputed       INTEGER NOT NULL DEFAULT 0,
    created_by     TEXT,
    created_at     TEXT NOT NULL,
    analysed_at    TEXT,
    updated_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id   TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    key       TEXT NOT NULL,
    payload   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id   TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    ext       TEXT NOT NULL,
    sha256    TEXT NOT NULL,
    size      INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    decision    TEXT NOT NULL,
    notes       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS appeals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    recorded_by TEXT NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id   TEXT,
    actor     TEXT NOT NULL,
    event     TEXT NOT NULL,
    details   TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_case ON signals(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_events(case_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)


# ---------- cases ----------
def create_case(case_id: str, candidate_ref: str, session_id: str, created_by: str,
                is_demo: bool = False, demo_scenario: Optional[str] = None) -> None:
    ts = now()
    with connect() as c:
        c.execute(
            "INSERT INTO cases (case_id, candidate_ref, session_id, is_demo, demo_scenario, status,"
            " created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (case_id, candidate_ref, session_id, int(is_demo), demo_scenario,
             CaseStatus.DRAFT.value, created_by, ts, ts))


def get_case(case_id: str) -> Optional[dict]:
    with connect() as c:
        row = c.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    return dict(row) if row else None


def list_cases(limit: int = 200) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM cases ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def save_analysis(case_id: str, signals: list[Signal], assessment: RiskAssessment) -> None:
    """Persist automated results.

    Automated analysis may only move a case from DRAFT to AWAITING_REVIEW. If a
    human has already decided, re-analysis never overwrites that decision.
    """
    ts = now()
    with connect() as c:
        c.execute("DELETE FROM signals WHERE case_id=?", (case_id,))
        c.executemany(
            "INSERT INTO signals (case_id, key, payload, created_at) VALUES (?,?,?,?)",
            [(case_id, s.key, json.dumps(s.to_dict()), ts) for s in signals])
        c.execute(
            "UPDATE cases SET risk_band=?, risk_score=?, assessment=?, analysed_at=?, updated_at=?,"
            " status = CASE WHEN status=? THEN ? ELSE status END WHERE case_id=?",
            (assessment.band.value, assessment.score, json.dumps(assessment.to_dict()), ts, ts,
             CaseStatus.DRAFT.value, CaseStatus.AWAITING_REVIEW.value, case_id))


def get_signals(case_id: str) -> list[Signal]:
    with connect() as c:
        rows = c.execute("SELECT payload FROM signals WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
    return [Signal.from_dict(json.loads(r["payload"])) for r in rows]


def get_assessment(case: dict) -> Optional[RiskAssessment]:
    if not case or not case.get("assessment"):
        return None
    return RiskAssessment.from_dict(json.loads(case["assessment"]))


def _set_status_by_human(conn: sqlite3.Connection, case_id: str, status: CaseStatus) -> None:
    """Private: only services.reviewer calls this, after validating a human reviewer."""
    conn.execute("UPDATE cases SET status=?, updated_at=? WHERE case_id=?",
                 (status.value, now(), case_id))


# ---------- files ----------
def add_file(case_id: str, kind: str, stored_path: str, ext: str, sha256: str, size: int) -> None:
    with connect() as c:
        c.execute("INSERT INTO files (case_id, kind, stored_path, ext, sha256, size, uploaded_at)"
                  " VALUES (?,?,?,?,?,?,?)", (case_id, kind, stored_path, ext, sha256, size, now()))


def get_files(case_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM files WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
    return [dict(r) for r in rows]


# ---------- decisions / appeals ----------
def get_decisions(case_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM decisions WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
    return [dict(r) for r in rows]


def get_appeals(case_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM appeals WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
    return [dict(r) for r in rows]


# ---------- audit ----------
def add_audit(case_id: Optional[str], actor: str, event: str, details: Any = None,
              conn: Optional[sqlite3.Connection] = None) -> None:
    payload = json.dumps(details) if details is not None else None
    sql = "INSERT INTO audit_events (case_id, actor, event, details, created_at) VALUES (?,?,?,?,?)"
    if conn is not None:
        conn.execute(sql, (case_id, actor, event, payload, now()))
        return
    with connect() as c:
        c.execute(sql, (case_id, actor, event, payload, now()))


def get_audit(case_id: Optional[str] = None, limit: int = 200) -> list[dict]:
    with connect() as c:
        if case_id:
            rows = c.execute("SELECT * FROM audit_events WHERE case_id=? ORDER BY id DESC LIMIT ?",
                             (case_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"]) if d["details"] else None
        out.append(d)
    return out


def delete_case_rows(case_id: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM cases WHERE case_id=?", (case_id,))
        # Audit trail keeps a tombstone only: personal details are removed.
        c.execute("UPDATE audit_events SET details=NULL WHERE case_id=?", (case_id,))


def stats() -> dict:
    with connect() as c:
        total = c.execute("SELECT COUNT(*) FROM cases WHERE status != ?", (CaseStatus.DRAFT.value,)).fetchone()[0]
        awaiting = c.execute("SELECT COUNT(*) FROM cases WHERE status IN (?,?)",
                             (CaseStatus.AWAITING_REVIEW.value, CaseStatus.FURTHER_REVIEW.value)).fetchone()[0]
        inconclusive = c.execute("SELECT COUNT(*) FROM cases WHERE risk_band='Inconclusive'").fetchone()[0]
        decided = c.execute("SELECT COUNT(*) FROM cases WHERE status IN (?,?)",
                            (CaseStatus.VERIFIED.value, CaseStatus.CONFIRMED_CONCERN.value)).fetchone()[0]
        disputed = c.execute("SELECT COUNT(*) FROM cases WHERE disputed=1").fetchone()[0]
        bands = {r[0]: r[1] for r in c.execute(
            "SELECT risk_band, COUNT(*) FROM cases WHERE risk_band IS NOT NULL GROUP BY risk_band")}
        statuses = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM cases GROUP BY status")}
    return dict(total=total, awaiting=awaiting, inconclusive=inconclusive, decided=decided,
                disputed=disputed, bands=bands, statuses=statuses)
