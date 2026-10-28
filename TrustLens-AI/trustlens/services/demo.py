"""Clearly labelled demonstration cases built from synthetic files.

The checks run for real on these synthetic inputs — nothing is pre-scripted.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import audit
from .. import database as db
from ..pipeline import run_case
from ..security import new_case_id, store_upload
from . import sample_data


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    description: str
    files: dict  # upload kind -> sample key
    expected: str


SCENARIOS = {
    s.key: s for s in [
        Scenario("clean", "Clean document",
                 "An unedited synthetic certificate PDF and a specific, detailed statement.",
                 {"document": "genuine_certificate", "statement": "human_sop"}, "Low"),
        Scenario("tampered_pdf", "Edited certificate PDF",
                 "The same certificate with the grade covered by a white box and retyped, saved as an incremental update.",
                 {"document": "tampered_certificate"}, "Moderate"),
        Scenario("replay_plus_doc", "Replayed video + edited PDF",
                 "A 2-second clip played three times in a row, plus the edited certificate.",
                 {"capture_video": "replay_video", "document": "tampered_certificate"}, "Elevated"),
        Scenario("poor_quality", "Poor-quality capture",
                 "A dark, blurry, 1.5-second, low-resolution video and nothing else.",
                 {"capture_video": "poor_video"}, "Inconclusive"),
        Scenario("generic_statement", "Generic statement (weak signal)",
                 "An unedited certificate with a statement full of stock phrases. Shows the weak-signal cap.",
                 {"document": "genuine_certificate", "statement": "ai_sop"}, "Low"),
        Scenario("edited_scan", "Edited certificate scan (JPEG)",
                 "A scanned certificate image with a pasted-in grade region.",
                 {"document": "tampered_scan"}, "Moderate"),
    ]
}


def create_demo_case(scenario_key: str, actor: str, progress=None) -> str:
    sc = SCENARIOS[scenario_key]
    paths = sample_data.generate_all()
    case_id = new_case_id()
    db.create_case(case_id, f"DEMO-{scenario_key.upper()}", "DEMO-SESSION", actor,
                   is_demo=True, demo_scenario=scenario_key)
    audit.log("demo_case_created", actor, case_id, scenario=scenario_key)
    for kind, sample_key in sc.files.items():
        p = paths[sample_key]
        stored = store_upload(case_id, kind, p.name, p.read_bytes())
        db.add_file(case_id, kind, str(stored.path), stored.ext, stored.sha256, stored.size)
    run_case(case_id, actor, progress)
    return case_id
