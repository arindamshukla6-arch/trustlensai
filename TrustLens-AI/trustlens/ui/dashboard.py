from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import database as db
from ..models import STATUS_LABELS, CaseStatus
from . import state, theme


def render() -> None:
    theme.hero("Evidence for humans. Never auto-verdicts.",
               "TrustLens screens identity captures and documents for exams and admissions, then hands a "
               "reviewer an explainable evidence dossier. It never rejects a candidate on its own.")
    s = db.stats()
    c = st.columns(4)
    with c[0]:
        theme.metric("Cases analysed", s["total"], "Cases where the automated checks have run at least once.")
    with c[1]:
        theme.metric("Awaiting human review", s["awaiting"], "Analysed cases with no final decision yet, including those sent for further review.")
    with c[2]:
        theme.metric("Inconclusive", s["inconclusive"], "Not enough usable evidence to give a band. Usually fixed by a recapture.")
    with c[3]:
        theme.metric("Decided by a reviewer", s["decided"], f"Verified or confirmed concern by a named human. {s['disputed']} disputed.")
    st.write("")

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Advisory bands")
        bands = ["Low", "Moderate", "Elevated", "Inconclusive"]
        vals = [s["bands"].get(b, 0) for b in bands]
        if sum(vals):
            fig = go.Figure(go.Bar(x=bands, y=vals, marker_color=[theme.BAND_HEX[b] for b in bands],
                                   text=vals, textposition="outside"))
            fig.update_layout(**theme.PLOT_LAYOUT, height=280, yaxis_title="Cases")
            st.plotly_chart(fig, width="stretch")
        else:
            theme.empty("No analysed cases yet. Sign in and run a demo case from New verification.")
    with right:
        st.subheader("Review status")
        labels = {k.value: v for k, v in STATUS_LABELS.items()}
        rows = [{"Status": labels.get(k, k), "Cases": v} for k, v in s["statuses"].items() if k != CaseStatus.DRAFT.value]
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            theme.empty("Nothing to review yet.")

    st.subheader("Recent activity")
    events = db.get_audit(limit=15)
    if events:
        st.dataframe(pd.DataFrame([{"Time (UTC)": ev["created_at"].replace("T", " ").replace("+00:00", ""),
                                    "Event": ev["event"].replace("_", " "),
                                    "Case": ev["case_id"] or "",
                                    "Actor": ev["actor"] if state.authed() else "hidden"} for ev in events]),
                     width="stretch", hide_index=True)
    else:
        theme.empty("No activity recorded yet.")
    st.caption("This dashboard shows aggregate counts and random case IDs only. Candidate IDs, files and "
               "evidence are visible only to signed-in reviewers.")
