from __future__ import annotations

import time

import cv2
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import audit
from .. import database as db
from ..modules import challenge
from ..pipeline import rescore_with
from ..security import store_upload
from . import components, state, theme


def _decode(upload) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(upload.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Snapshot could not be decoded.")
    return img


def render() -> None:
    st.header("Liveness and replay screening")
    theme.note("Preliminary presentation-attack screening. These checks look for frozen frames, replayed loops and "
               "whether a face moved as instructed. They cannot prove a video is live and do not detect deepfakes.")
    if not state.require_auth():
        return
    case = state.case_picker()
    if not case:
        theme.empty("No cases yet. Create one in New verification.")
        return
    if case["is_demo"]:
        theme.demo_banner()
    sig = {s.key: s for s in db.get_signals(case["case_id"])}
    v = sig.get("video_replay")

    tab1, tab2 = st.tabs(["Video replay analysis", "Live challenge-response"])
    with tab1:
        if not v:
            theme.empty("This case has not been analysed.")
        else:
            components.signal_card(v, expanded=False)
            m = v.metrics
            if m.get("frame_diff_series"):
                fig = go.Figure(go.Scatter(x=m["frame_times"], y=m["frame_diff_series"], mode="lines",
                                           line=dict(color="#22D3EE", width=2), name="Change between frames"))
                for a, b in m.get("frozen_runs", []):
                    fig.add_vrect(x0=a, x1=b, fillcolor="#FBBF24", opacity=0.18, line_width=0,
                                  annotation_text="frozen", annotation_position="top left")
                for lp in m.get("loops", []):
                    fig.add_vrect(x0=lp["repeat_start"], x1=lp["repeat_end"], fillcolor="#F87171", opacity=0.16,
                                  line_width=0, annotation_text="repeat", annotation_position="top left")
                fig.update_layout(**theme.PLOT_LAYOUT, height=300, xaxis_title="Time (s)",
                                  yaxis_title="Mean abs. difference (0–255)")
                st.plotly_chart(fig, width="stretch")
                st.caption("Each point is how much the picture changed since the previous sampled frame. "
                           "Shaded bands mark flagged timestamps.")
            if m.get("loops"):
                st.markdown("**Repeated segments**")
                st.dataframe(pd.DataFrame(m["loops"]), width="stretch", hide_index=True)
            cols = st.columns(4)
            for c, (k, label) in zip(cols, [("frames_total", "Frames"), ("duration_s", "Seconds"),
                                            ("single_face_frames", "Frames with one face"), ("median_sharpness", "Sharpness")]):
                if k in m:
                    c.metric(label, m[k])

    with tab2:
        st.caption("The challenge is chosen at random when you press the button and expires after a short time.")
        if st.button("Issue a new challenge"):
            st.session_state["challenge"] = challenge.issue().to_dict()
            audit.log("challenge_issued", state.reviewer(), case["case_id"], code=st.session_state["challenge"]["code"])
        ch = st.session_state.get("challenge")
        if ch:
            remaining = int(ch["issued_at"] + challenge.settings.challenge_ttl_seconds - time.time())
            st.markdown(f"### {ch['instruction']}")
            st.caption(f"Challenge {ch['nonce']} — {max(0, remaining)}s left when this page was drawn.")
            c1, c2 = st.columns(2)
            base = c1.camera_input("1. Baseline: look at the camera", key="cam_base")
            resp = c2.camera_input("2. Now follow the instruction", key="cam_resp")
            if base and resp and st.button("Evaluate challenge", type="primary"):
                try:
                    s = challenge.evaluate(challenge.Challenge(**ch), _decode(base), _decode(resp))
                    for kind, up in (("challenge_baseline", base), ("challenge_response", resp)):
                        sf = store_upload(case["case_id"], kind, "snap.jpg" if up.type == "image/jpeg" else "snap.png", up.getvalue())
                        db.add_file(case["case_id"], kind, str(sf.path), sf.ext, sf.sha256, sf.size)
                    rescore_with(case["case_id"], state.reviewer(), s)
                    st.session_state.pop("challenge", None)
                    components.signal_card(s, expanded=True)
                except Exception as ex:
                    st.error(f"The challenge could not be evaluated: {ex}")
        elif (c := sig.get("challenge_response")):
            components.signal_card(c)
