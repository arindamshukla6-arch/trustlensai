# TrustLens AI — Evidence for Humans. Never Auto-Verdicts.

**Team 4A SQUAD · CODE Yudh Hackathon, Chandigarh University**

TrustLens AI screens identity captures and documents for online exams and admissions, then produces an
explainable **evidence dossier** for a human reviewer. It never rejects a candidate. Automated checks can
only move a case to *Awaiting human review*; only a signed-in reviewer can record a decision, and every
decision can be disputed.

## What is actually implemented

| Check | How it works | Honest limits |
|---|---|---|
| Replay screening (video) | OpenCV frame sampling; frozen-frame runs; repeated-segment (loop) search that requires the scene to change in between; face presence, brightness, sharpness | Preliminary. Does not detect deepfakes, masks, screen replays or virtual cameras |
| Live challenge-response | Random instruction (`secrets`), two webcam snapshots, face-box displacement, identical-snapshot check, expiry | Passable by a live deepfake or a cooperating impostor |
| Face matching | OpenCV **YuNet** detector + **SFace** embeddings, cosine similarity vs OpenCV's published threshold with an uncertainty band | Not proof of identity; unvalidated threshold; uneven accuracy across groups possible. If the model is missing it reports **Not run** — never simulated |
| PDF structure | Incremental revisions, white covering rectangles, appended content streams, overlay annotations, JavaScript, embedded files, signature fields, text layer vs OCR | Signatures detected, **not** cryptographically validated. No issuer database integration |
| PDF metadata | Date order, future dates, editing-tool producers | Metadata anomalies are not proof of forgery |
| Image forensics (JPEG) | EXIF; edge-normalised error-level analysis at JPEG qualities 70–95 with a heatmap | Re-saving and screenshots erase or distort traces |
| Statement style (weak) | Sentence-length variation, vocabulary diversity, stock phrases, concrete-detail rate | **Not an AI detector.** Capped so it can never raise a case above Low by itself |

Every signal stores: name, result, evidence, input quality, method, limitations, and confidence **only where
genuinely calculated** (none of the heuristics claim one).

## Risk aggregation (transparent and configurable)

* Results: `no_concern`, `concern`, `inconclusive`, `not_run`, `error`. Only the first two count as completed.
* Missing, failed or inconclusive checks **add nothing** — absence is never suspicious.
* If no core check completed → **Inconclusive** (with a recapture recommendation where quality was the cause).
* `score = Σ weight × severity` over `concern` signals; Low < 0.20 ≤ Moderate < 0.45 ≤ Elevated.
* All weights and thresholds live in `.env`. **They are unvalidated prototype defaults** and need empirical
  calibration on consented, representative data before any real use. No demographic attribute is used.

## Quick start (any OS)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # macOS/Linux: cp .env.example .env
python scripts/download_models.py   # optional, enables face matching (~37 MB)
python scripts/generate_sample_data.py
streamlit run app.py
```

Sign in from the sidebar with any reviewer ID (e.g. `rev.sharma`) and the access code from `.env`
(default `change-me` — change it). Then go to **New verification → Try demo case**.

Run the tests: `python -m pytest -q`

Full Windows walkthrough: [`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md) · Demo script, test cases and judge
Q&A: [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md)

## Project layout

```
app.py                      Streamlit entry point and navigation
trustlens/
  config.py                 .env-driven settings, weights, thresholds
  models.py                 Signal, Finding, RiskAssessment, CaseStatus (no automatic 'rejected')
  scoring.py                Rule-based advisory aggregation (no database access)
  database.py  audit.py     SQLite schema, persistence, audit trail
  security.py               Upload validation, random storage names, access code
  pipeline.py               Runs checks; sets AWAITING_REVIEW only
  modules/                  video_analysis, challenge, face_backend, face_matching,
                            document_forensics, text_analysis, image_quality
  services/                 dossier (JSON + PDF), reviewer (only path to a decision),
                            retention, demo scenarios, synthetic sample_data
  ui/                       One module per page + theme and components
scripts/                    download_models.py, generate_sample_data.py
tests/                      33 pytest tests
sample_data/                Synthetic files only (see README_SYNTHETIC.txt)
```

## Privacy and responsible-AI controls

Pseudonymous candidate IDs; original filenames discarded; extension **and** content checks on every upload;
size limits; evidence visible only after sign-in; public dashboard shows counts and random case IDs; automatic
retention purge (`RETENTION_DAYS`); per-case deletion; dispute/appeal recording; full audit trail; visible
limitation notices on every page; demo cases watermarked in the UI and the PDF.

**Prototype access control is a shared access code, not production authentication.** Use synthetic or
consented data only.

## Licences of third-party models

OpenCV YuNet (MIT) and SFace (Apache-2.0) from the OpenCV Model Zoo. Haar cascade ships with OpenCV.
