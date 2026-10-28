from __future__ import annotations

import streamlit as st

from .. import database as db
from ..modules import face_backend
from . import components, state, theme


def render() -> None:
    st.header("Face matching")
    caps = face_backend.capability_report()
    c1, c2, c3 = st.columns(3)
    c1.metric("Face detector", caps["detector"].split(" (")[0])
    c2.metric("Embedding model", caps["embedding_model"].split(" (")[0])
    c3.metric("Matching available", "Yes" if caps["face_matching_available"] else "No")
    if not caps["face_matching_available"]:
        st.warning("The SFace embedding model is not installed, so face matching reports **Not run**. "
                   "It is never simulated. Install it with `python scripts/download_models.py`.")
    theme.note("Similarity measures how alike two face images look to the model. It is not proof of identity, "
               "and it is not a probability. Results inside the uncertainty band around the threshold are "
               "reported as inconclusive. No-face and multiple-face images are never scored.")
    if not state.require_auth():
        return
    case = state.case_picker()
    if not case:
        theme.empty("No cases yet. Create one in New verification.")
        return
    s = next((x for x in db.get_signals(case["case_id"]) if x.key == "face_match"), None)
    if case["is_demo"]:
        theme.demo_banner()
        st.caption("Demo cases contain no faces (no real people's images are shipped). Upload consented photos "
                   "of your own team in New verification to demonstrate matching.")
    if not s:
        theme.empty("This case has not been analysed.")
        return
    components.signal_card(s, expanded=True)
    m = s.metrics
    if "similarity" in m:
        import plotly.graph_objects as go
        thr, mg = m["threshold"], m["margin"]
        fig = go.Figure()
        fig.add_vrect(x0=thr - mg, x1=thr + mg, fillcolor="#FBBF24", opacity=0.15, line_width=0,
                      annotation_text="uncertain", annotation_position="top")
        fig.add_vline(x=thr, line_color="#A9BAD1", line_dash="dash")
        fig.add_trace(go.Scatter(x=[m["similarity"]], y=[0], mode="markers", marker=dict(size=18, color="#22D3EE")))
        fig.update_layout(**theme.PLOT_LAYOUT, height=160, xaxis_range=[-0.2, 1.0], showlegend=False)
        fig.update_yaxes(visible=False)
        st.plotly_chart(fig, width="stretch")
