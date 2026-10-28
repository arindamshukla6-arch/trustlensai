from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import database as db
from ..models import DECISION_LABELS, HUMAN_DECISIONS, STATUS_LABELS, CaseStatus
from ..services import retention, reviewer
from . import components, state, theme


def render() -> None:
    st.header("Reviewer panel")
    if not state.require_auth():
        return
    case = state.case_picker()
    if not case:
        theme.empty("No cases to review. Create one in New verification.")
        return
    cid = case["case_id"]
    status = CaseStatus(case["status"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Current status", STATUS_LABELS[status])
    c2.markdown(f"Advisory band<br>{theme.badge(case['risk_band'])}", unsafe_allow_html=True)
    c3.metric("Disputed", "Yes" if case["disputed"] else "No")
    components.risk_summary(case, db.get_assessment(case))
    with st.expander("View the full signal list"):
        for s in db.get_signals(cid):
            components.signal_card(s)

    st.subheader("Record a decision")
    theme.note("Your decision is the only thing that can change this case's status. The advisory band is "
               "context, not an instruction. Record the reasons a colleague would need to understand your call.")
    with st.form("decision"):
        choice = st.radio("Decision", HUMAN_DECISIONS, format_func=lambda d: DECISION_LABELS[d], horizontal=True)
        notes = st.text_area("Reasons and evidence reviewed", height=120,
                             placeholder="e.g. Compared the certificate with the issuer by phone on …")
        rid = st.text_input("Reviewer ID", value=state.reviewer(), disabled=True)
        if st.form_submit_button("Record decision", type="primary"):
            try:
                reviewer.record_decision(cid, rid, choice, notes, authorised=state.authed())
                st.success(f"Decision recorded: {DECISION_LABELS[choice]}.")
                st.rerun()
            except reviewer.ReviewError as ex:
                st.error(str(ex))

    decisions = db.get_decisions(cid)
    st.subheader("Decision history")
    if decisions:
        st.dataframe(pd.DataFrame([{"Time (UTC)": d["created_at"], "Reviewer": d["reviewer_id"],
                                    "Decision": DECISION_LABELS[CaseStatus(d["decision"])], "Notes": d["notes"]}
                                   for d in decisions]), width="stretch", hide_index=True)
    else:
        theme.empty("No human decision yet. The case has no final status.")

    st.subheader("Dispute or appeal")
    with st.form("appeal"):
        reason = st.text_area("Candidate's dispute, as they described it", height=90)
        if st.form_submit_button("Mark as disputed and record appeal"):
            try:
                reviewer.record_appeal(cid, state.reviewer(), reason, authorised=state.authed())
                st.success("Appeal recorded and case marked as disputed.")
                st.rerun()
            except reviewer.ReviewError as ex:
                st.error(str(ex))
    appeals = db.get_appeals(cid)
    if appeals:
        st.dataframe(pd.DataFrame(appeals)[["created_at", "recorded_by", "reason", "status"]],
                     width="stretch", hide_index=True)

    st.subheader("Audit trail")
    events = db.get_audit(cid)
    st.dataframe(pd.DataFrame([{"Time (UTC)": e["created_at"], "Actor": e["actor"], "Event": e["event"].replace("_", " "),
                                "Details": "" if not e["details"] else str(e["details"])[:160]} for e in events]),
                 width="stretch", hide_index=True)

    with st.expander("Delete this case"):
        st.caption("Removes uploaded files, signals, decisions and appeals. A minimal audit record of the deletion is kept.")
        confirm = st.text_input(f"Type {cid} to confirm")
        if st.button("Delete case permanently", disabled=confirm != cid):
            retention.delete_case(cid, state.reviewer())
            st.session_state.pop("active_case", None)
            st.session_state.pop("last_run", None)
            st.success("Case deleted.")
            st.rerun()
