"""Session helpers: sign-in and the active case."""
from __future__ import annotations

import streamlit as st

from .. import audit
from .. import database as db
from ..security import check_access_code, valid_reviewer_id


def authed() -> bool:
    return bool(st.session_state.get("authed"))


def reviewer() -> str:
    return st.session_state.get("reviewer_id", "")


def sign_in_box() -> None:
    if authed():
        st.caption(f"Signed in as **{reviewer()}**")
        if st.button("Sign out", width="stretch"):
            audit.log("signed_out", reviewer())
            for k in ("authed", "reviewer_id", "active_case"):
                st.session_state.pop(k, None)
            st.rerun()
        return
    with st.form("signin", clear_on_submit=False):
        st.markdown("**Reviewer sign-in**")
        rid = st.text_input("Reviewer ID", placeholder="e.g. rev.sharma")
        code = st.text_input("Access code", type="password", help="Set REVIEWER_ACCESS_CODE in your .env file.")
        if st.form_submit_button("Sign in", width="stretch"):
            if not valid_reviewer_id(rid):
                st.error("Reviewer ID must be 2–40 letters, digits, dots, dashes or underscores.")
            elif not check_access_code(code):
                audit.log("sign_in_failed", rid)
                st.error("That access code is not correct.")
            else:
                st.session_state.update(authed=True, reviewer_id=rid)
                audit.log("signed_in", rid)
                st.rerun()


def require_auth() -> bool:
    if authed():
        return True
    st.info("Sign in with the reviewer access code in the sidebar to view cases, evidence and uploaded files.")
    return False


def case_picker(label: str = "Case") -> dict | None:
    cases = db.list_cases()
    if not cases:
        return None
    ids = [c["case_id"] for c in cases]
    active = st.session_state.get("active_case")
    idx = ids.index(active) if active in ids else 0
    fmt = {c["case_id"]: f"{c['case_id']}  ({'demo, ' if c['is_demo'] else ''}{c['risk_band'] or 'not analysed'})" for c in cases}
    choice = st.selectbox(label, ids, index=idx, format_func=lambda x: fmt[x])
    st.session_state["active_case"] = choice
    return db.get_case(choice)
