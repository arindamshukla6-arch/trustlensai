from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import audit
from .. import database as db
from ..services import dossier
from . import components, state, theme


def render() -> None:
    st.header("Evidence dossier")
    if not state.require_auth():
        return
    case = state.case_picker()
    if not case:
        theme.empty("No cases yet. Create one in New verification.")
        return
    a = db.get_assessment(case)
    signals = db.get_signals(case["case_id"])
    c = st.columns(4)
    c[0].markdown(f"**Case**<br>{theme.e(case['case_id'])}", unsafe_allow_html=True)
    c[1].markdown(f"**Candidate**<br>{theme.e(case['candidate_ref'])}", unsafe_allow_html=True)
    c[2].markdown(f"**Session**<br>{theme.e(case['session_id'])}", unsafe_allow_html=True)
    c[3].markdown(f"**Analysed (UTC)**<br>{theme.e((case['analysed_at'] or '—').replace('T', ' '))}", unsafe_allow_html=True)
    st.write("")
    components.risk_summary(case, a)
    if not a:
        return

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Signals")
        components.signals_table(signals)
    with right:
        st.subheader("What moved the score")
        if a.contributions:
            names = {s.key: s.name for s in signals}
            fig = go.Figure(go.Bar(y=[names.get(k, k) for k in a.contributions], x=list(a.contributions.values()),
                                   orientation="h", marker_color="#22D3EE"))
            from ..config import settings
            fig.add_vline(x=settings.moderate_threshold, line_dash="dot", line_color="#FBBF24",
                          annotation_text="moderate", annotation_position="top")
            fig.add_vline(x=settings.elevated_threshold, line_dash="dot", line_color="#F87171",
                          annotation_text="elevated", annotation_position="top")
            fig.update_layout(**theme.PLOT_LAYOUT, height=240, xaxis_title="Contribution (weight × severity)")
            st.plotly_chart(fig, width="stretch")
        else:
            theme.empty("No signal contributed to the score.")

    st.subheader("Evidence by signal")
    for s in signals:
        components.signal_card(s)

    incomplete = [s for s in signals if not s.result.completed]
    if incomplete:
        st.subheader("Checks that could not be completed")
        st.dataframe(pd.DataFrame([{"Signal": s.name, "State": theme.RESULT_TEXT[s.result.value],
                                    "Reason": s.error or " ".join(s.evidence)} for s in incomplete]),
                     width="stretch", hide_index=True)

    st.subheader("Suggested next steps")
    for i, step in enumerate(a.next_steps, 1):
        st.markdown(f"{i}. {step}")
    theme.note(dossier.CONFIDENCE_NOTE)

    st.subheader("Export")
    d = dossier.build(case["case_id"])
    c1, c2 = st.columns(2)
    if c1.download_button("Download JSON", dossier.to_json(d), file_name=f"{case['case_id']}_dossier.json",
                          mime="application/json", width="stretch"):
        audit.log("dossier_exported", state.reviewer(), case["case_id"], format="json")
    try:
        pdf = dossier.to_pdf(d)
        if c2.download_button("Download PDF report", pdf, file_name=f"{case['case_id']}_dossier.pdf",
                              mime="application/pdf", width="stretch"):
            audit.log("dossier_exported", state.reviewer(), case["case_id"], format="pdf")
    except Exception as ex:
        c2.error(f"PDF report could not be generated: {ex}")
