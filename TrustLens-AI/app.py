"""TrustLens AI — Evidence for Humans. Never Auto-Verdicts.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="TrustLens AI", page_icon="🔎", layout="wide")

from trustlens import __version__  # noqa: E402
from trustlens import database as db  # noqa: E402
from trustlens.services import retention  # noqa: E402
from trustlens.ui import (dashboard, documents, dossier_page, face, liveness, privacy,  # noqa: E402
                          reviewer_page, state, theme, verify)

PAGES = {
    "Dashboard": dashboard.render,
    "New verification": verify.render,
    "Liveness and replay": liveness.render,
    "Face matching": face.render,
    "Document forensics": documents.render,
    "Evidence dossier": dossier_page.render,
    "Reviewer panel": reviewer_page.render,
    "Privacy and limits": privacy.render,
}


@st.cache_resource
def _startup() -> int:
    db.init_db()
    return retention.purge_expired()


def main() -> None:
    theme.inject()
    _startup()
    with st.sidebar:
        theme.brand()
        page = st.radio("Navigate", list(PAGES), label_visibility="collapsed")
        st.divider()
        state.sign_in_box()
        st.divider()
        st.caption(f"Built by 4A SQUAD for CODE Yudh, Chandigarh University. v{__version__}")
        st.caption("Prototype. Signals for human reviewers, never automatic decisions.")
    PAGES[page]()


main()
