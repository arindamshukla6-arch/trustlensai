from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from .. import database as db
from . import components, state, theme


def render() -> None:
    st.header("Document forensics")
    theme.note("These checks look at how a file was produced and changed. A metadata anomaly is not proof of forgery, "
               "and nothing here verifies a certificate with the issuing institution — no such integration exists.")
    if not state.require_auth():
        return
    case = state.case_picker()
    if not case:
        theme.empty("No cases yet. Create one in New verification.")
        return
    if case["is_demo"]:
        theme.demo_banner()
    sigs = [s for s in db.get_signals(case["case_id"]) if s.key in ("doc_integrity", "doc_metadata", "image_forensics")]
    if not sigs:
        theme.empty("No document was analysed for this case.")
        return
    for s in sigs:
        components.signal_card(s, expanded=s.result.value == "concern")
    integ = next((s for s in sigs if s.key == "doc_integrity"), None)
    meta = next((s for s in sigs if s.key == "doc_metadata"), None)
    img = next((s for s in sigs if s.key == "image_forensics"), None)
    c1, c2 = st.columns(2)
    if integ and integ.metrics.get("text_excerpt"):
        with c1:
            st.markdown("**Extracted text layer**")
            st.code(integ.metrics["text_excerpt"][:1000], language=None)
    if integ and (p := integ.metrics.get("page_render")) and Path(p).exists():
        with c2:
            st.image(p, caption="Page 1 as rendered (what a person sees)", width="stretch")
    if meta and meta.metrics.get("fields"):
        st.markdown("**Metadata fields**")
        st.dataframe(pd.DataFrame([{"Field": k, "Value": v} for k, v in meta.metrics["fields"].items()]),
                     width="stretch", hide_index=True)
    if img and img.metrics.get("ocr_excerpt"):
        st.markdown("**OCR text from image**")
        st.code(img.metrics["ocr_excerpt"], language=None)
