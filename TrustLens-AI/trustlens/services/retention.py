"""Data minimisation: case deletion and retention purge."""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone

from .. import database as db
from ..config import settings
from ..security import is_valid_case_id


def delete_case(case_id: str, actor: str, reason: str = "manual deletion") -> bool:
    if not is_valid_case_id(case_id) or not db.get_case(case_id):
        return False
    folder = settings.cases_dir / case_id
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    db.delete_case_rows(case_id)
    db.add_audit(case_id, actor, "case_deleted", {"reason": reason})
    return True


def purge_expired(actor: str = "retention-job") -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    removed = 0
    for case in db.list_cases(limit=100000):
        try:
            created = datetime.fromisoformat(case["created_at"])
        except ValueError:
            continue
        if created < cutoff and delete_case(case["case_id"], actor, f"retention > {settings.retention_days} days"):
            removed += 1
    return removed
