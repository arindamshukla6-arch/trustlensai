from __future__ import annotations

import streamlit as st

from ..config import settings
from ..modules import document_forensics, face_backend
from ..services import retention
from . import state, theme


def render() -> None:
    st.header("Privacy, limits and responsible use")
    st.markdown(f"""
**How TrustLens is meant to be used.** It produces signals for a trained human reviewer. It never rejects,
fails or blocks a candidate. Only a signed-in reviewer can record a decision, and every decision can be disputed.

**What it can and cannot tell you**
- Replay screening finds frozen stretches and repeated segments. It does not detect deepfakes, masks, screen replays or virtual cameras.
- Face matching reports a similarity score from OpenCV SFace. It is not proof of identity and may perform unevenly across groups.
- Document checks find editing traces and metadata anomalies. They do not confirm a certificate with its issuer.
- The statement style indicator is weak. Formal and non-native-English writing is often flagged. **Never treat it as proof of AI use.**
- All weights and thresholds are unvalidated prototype defaults in `.env`. They need empirical calibration before real use.
- No demographic or sensitive characteristic is used anywhere in scoring.

**Data handling**
- Files are stored under random server-side names in `data/cases/<case ID>/`; original filenames are discarded.
- Uploads are checked by extension and by content, and limited to {settings.max_upload_mb} MB.
- Cases older than **{settings.retention_days} days** are purged automatically when the app starts. Reviewers can delete any case.
- The public dashboard shows counts and random case IDs only. Evidence requires sign-in.
- Use synthetic or consented data only. This prototype is not certified for production use.
""")
    st.subheader("Installed capabilities")
    caps = face_backend.capability_report()
    st.dataframe({"Capability": ["Face detector", "Face embeddings", "OCR (Tesseract)"],
                  "Status": [caps["detector"], caps["embedding_model"],
                             "installed" if document_forensics._tesseract_available() else "not installed"]},
                 width="stretch", hide_index=True)
    if settings.reviewer_access_code == "change-me":
        st.warning("The reviewer access code is still the default. Set REVIEWER_ACCESS_CODE in .env.")
    if state.authed():
        if st.button("Run retention purge now"):
            n = retention.purge_expired(state.reviewer())
            st.success(f"Removed {n} expired case(s).")
