"""Thin audit helper so every module records events the same way."""
from __future__ import annotations

from typing import Any, Optional

from . import database as db


def log(event: str, actor: str, case_id: Optional[str] = None, **details: Any) -> None:
    db.add_audit(case_id, actor or "system", event, details or None)


def history(case_id: str) -> list[dict]:
    return db.get_audit(case_id)
