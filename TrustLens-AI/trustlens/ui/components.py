"""Reusable evidence widgets."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from ..models import Signal
from . import theme
from .theme import e


def signal_card(s: Signal, show_artifacts: bool = True, expanded: bool = False) -> None:
    conf = (f"{s.confidence:.2f} ({s.confidence_basis})" if s.confidence is not None else "Not calculated")
    sim = s.metrics.get("similarity")
    meas = f"Similarity {sim:.3f} vs threshold {s.metrics.get('threshold'):.3f}" if sim is not None else ""
    st.markdown(
        f'<div class="tl-signal"><h4>{e(s.name)} &nbsp;{theme.chip(s.result.value)}</h4>'
        f'<div class="m">Input quality: <b>{e(s.quality.value)}</b>&nbsp;&nbsp; Confidence: {e(conf)}'
        f'{("&nbsp;&nbsp; " + e(meas)) if meas else ""}</div>'
        f'<ul>{"".join(f"<li>{e(x)}</li>" for x in s.evidence)}</ul></div>', unsafe_allow_html=True)
    with st.expander("Method, findings and limitations", expanded=expanded):
        st.markdown(f"**Method:** {s.method or 'n/a'}")
        if s.error:
            st.error(f"Error detail: {s.error}")
        if s.recapture_recommended:
            st.warning("Recapture recommended: the input quality was not sufficient for a reliable result.")
        if s.findings:
            st.dataframe(pd.DataFrame([{
                "Check": f.check, "Observation": f.observation, "Severity": f.severity, "Where": f.location,
                "Can indicate": f.means, "Cannot establish": f.does_not_mean} for f in s.findings]),
                width="stretch", hide_index=True)
        if show_artifacts:
            for name, path in s.artifacts.items():
                if path and Path(path).exists():
                    st.image(path, caption=name.replace("_", " ").capitalize(), width="stretch")
        st.markdown("**Limitations**")
        for lim in s.limitations or ["None recorded."]:
            st.markdown(f"- {lim}")


def signals_table(signals: list[Signal]) -> None:
    rows = [{"Signal": s.name, "Result": theme.RESULT_TEXT[s.result.value], "Quality": s.quality.value,
             "Confidence": f"{s.confidence:.2f}" if s.confidence is not None else "not calculated",
             "Recapture": "yes" if s.recapture_recommended else ""} for s in signals]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def risk_summary(case: dict, assessment) -> None:
    if case.get("is_demo"):
        theme.demo_banner()
    if assessment is None:
        theme.empty("This case has not been analysed yet. Upload inputs and run the checks.")
        return
    c1, c2 = st.columns([1, 3])
    with c1:
        st.markdown("Advisory risk band")
        st.markdown(theme.badge(assessment.band.value), unsafe_allow_html=True)
        st.caption(f"Indicator score {assessment.score:.3f}")
    with c2:
        for r in assessment.reasons[:6]:
            st.markdown(f"- {r}")
    if assessment.recapture_recommended:
        st.warning("Recapture recommended for at least one input.")
    theme.note("The band is a triage aid, not a decision and not a probability of fraud. "
               "It cannot change the candidate's status; only a reviewer can.")
