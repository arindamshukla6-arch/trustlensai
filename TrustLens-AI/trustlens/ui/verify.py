from __future__ import annotations

import re

import streamlit as st

from .. import audit
from .. import database as db
from ..modules import face_backend
from ..pipeline import run_case
from ..security import UploadError, new_case_id, store_upload
from ..services import demo
from . import components, state, theme

UPLOADS = [
    ("reference_image", "Identity / reference photo", ["jpg", "jpeg", "png"]),
    ("capture_image", "Candidate capture photo", ["jpg", "jpeg", "png"]),
    ("capture_video", "Candidate capture video", ["mp4", "avi", "mov", "webm", "mkv"]),
    ("document", "Certificate or supporting document", ["pdf", "jpg", "jpeg", "png"]),
    ("statement", "Statement of purpose (optional)", ["txt", "pdf"]),
]


def _progress_ui():
    bar = st.progress(0.0, text="Starting…")
    return lambda msg, frac: bar.progress(min(1.0, max(0.0, frac)), text=msg)


def render() -> None:
    st.header("New verification")
    if not state.require_auth():
        return

    with st.container(border=True):
        st.markdown("**Try a demo case**")
        st.caption("Loads clearly labelled synthetic files and runs the real checks on them.")
        options = list(demo.SCENARIOS)
        key = st.selectbox("Scenario", options, format_func=lambda k: f"{demo.SCENARIOS[k].title} (expected: {demo.SCENARIOS[k].expected})")
        st.caption(demo.SCENARIOS[key].description)
        if st.button("Try demo case", type="primary"):
            with st.spinner("Generating synthetic files and running checks…"):
                try:
                    cid = demo.create_demo_case(key, state.reviewer(), _progress_ui())
                    st.session_state["active_case"] = cid
                    st.session_state["last_run"] = cid
                except Exception as ex:
                    st.error(f"The demo case could not be created: {ex}")

    results_slot = st.container()
    st.subheader("Verify a candidate")
    caps = face_backend.capability_report()
    if not caps["face_matching_available"]:
        st.warning("Face matching is unavailable: the SFace model is not installed. Run "
                   "`python scripts/download_models.py`. Other checks still work.")
    with st.form("new_case"):
        c1, c2 = st.columns(2)
        cand = c1.text_input("Candidate ID", max_chars=40, help="Use a pseudonymous ID, not a name.")
        sess = c2.text_input("Session ID", max_chars=40)
        files = {}
        cols = st.columns(2)
        for i, (kind, label, types) in enumerate(UPLOADS):
            files[kind] = cols[i % 2].file_uploader(label, type=types, key=f"up_{kind}")
        stmt_text = st.text_area("Or paste the statement text", height=120)
        consent = st.checkbox("I confirm the candidate consented to this check, or the files are synthetic test data.")
        go = st.form_submit_button("Run checks", type="primary")

    if go:
        pattern = r"[A-Za-z0-9._-]{2,40}"
        if not (re.fullmatch(pattern, cand or "") and re.fullmatch(pattern, sess or "")):
            st.error("Candidate ID and session ID must be 2–40 letters, digits, dots, dashes or underscores.")
        elif not consent:
            st.error("Confirm consent (or that the data is synthetic) before running checks.")
        elif not any(files.values()) and not stmt_text.strip():
            st.error("Upload at least one file or paste a statement.")
        else:
            cid = new_case_id()
            db.create_case(cid, cand, sess, state.reviewer())
            audit.log("case_created", state.reviewer(), cid)
            errors = []
            for kind, up in files.items():
                if up is None:
                    continue
                try:
                    sf = store_upload(cid, kind, up.name, up.getvalue())
                    db.add_file(cid, kind, str(sf.path), sf.ext, sf.sha256, sf.size)
                    audit.log("file_uploaded", state.reviewer(), cid, kind=kind, sha256=sf.sha256, size=sf.size)
                except UploadError as ex:
                    errors.append(f"{kind.replace('_', ' ').capitalize()}: {ex}")
            for er in errors:
                st.error(er)
            run_case(cid, state.reviewer(), _progress_ui(), statement_text=stmt_text or None)
            st.session_state["active_case"] = cid
            st.session_state["last_run"] = cid

    cid = st.session_state.get("last_run")
    case = db.get_case(cid) if cid else None
    if case:
        with results_slot:
            st.subheader(f"Results for {cid}")
            components.risk_summary(case, db.get_assessment(case))
            for sg in db.get_signals(cid):
                components.signal_card(sg)
            st.info("Open **Evidence dossier** to export the report, or **Reviewer panel** to record a decision.")
