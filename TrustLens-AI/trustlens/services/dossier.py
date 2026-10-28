"""Evidence dossier: structured JSON and a printable PDF report."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from .. import __version__
from .. import database as db
from ..models import STATUS_LABELS, CaseStatus, SignalResult
from ..scoring import DISCLAIMER
from ..security import mask

RESULT_LABELS = {
    "no_concern": "No concern found", "concern": "Indicator found", "inconclusive": "Inconclusive",
    "not_run": "Not run", "error": "Could not complete",
}

CONFIDENCE_NOTE = ("Model confidence, similarity and severity values describe how strongly a measurement "
                   "was observed. They are not the probability that a person committed fraud.")


def build(case_id: str, include_private: bool = True) -> dict:
    case = db.get_case(case_id)
    if not case:
        raise ValueError("Case not found.")
    signals = db.get_signals(case_id)
    assessment = db.get_assessment(case)
    return {
        "report": "TrustLens AI evidence dossier",
        "generator_version": __version__,
        "generated_at": db.now(),
        "demonstration": bool(case["is_demo"]),
        "demonstration_note": ("DEMONSTRATION CASE: inputs are synthetic test files. Results are real outputs "
                               "of the implemented checks on synthetic data.") if case["is_demo"] else None,
        "case": {
            "case_id": case["case_id"],
            "candidate_id": case["candidate_ref"] if include_private else mask(case["candidate_ref"]),
            "session_id": case["session_id"],
            "created_at": case["created_at"], "analysed_at": case["analysed_at"],
            "status": case["status"], "status_label": STATUS_LABELS.get(CaseStatus(case["status"]), case["status"]),
            "disputed": bool(case["disputed"]),
        },
        "advisory_risk": assessment.to_dict() if assessment else None,
        "signals": [s.to_dict() for s in signals],
        "checks_not_completed": [{"signal": s.name, "result": s.result.value, "reason": (s.error or "; ".join(s.evidence))}
                                 for s in signals if not s.result.completed],
        "files": [{"kind": f["kind"], "sha256": f["sha256"], "size": f["size"], "uploaded_at": f["uploaded_at"]}
                  for f in db.get_files(case_id)],
        "human_decisions": db.get_decisions(case_id),
        "appeals": db.get_appeals(case_id),
        "audit_events": db.get_audit(case_id),
        "confidence_note": CONFIDENCE_NOTE,
        "disclaimer": DISCLAIMER,
    }


def to_json(dossier: dict) -> bytes:
    def _strip(sig):
        sig = dict(sig)
        m = dict(sig.get("metrics", {}))
        m.pop("frame_diff_series", None)
        m.pop("frame_times", None)
        sig["metrics"] = m
        sig.pop("artifacts", None)  # server paths are not exported
        return sig
    d = dict(dossier, signals=[_strip(s) for s in dossier["signals"]])
    return json.dumps(d, indent=2, default=str).encode("utf-8")


# ------------------------------------------------------------------ PDF
NAVY = colors.HexColor("#0B1F3A")
CYAN = colors.HexColor("#0E9CB8")
INK = colors.HexColor("#1B2635")
MUTED = colors.HexColor("#5B6B80")
BAND_COLORS = {"Low": "#1F7A5A", "Moderate": "#9A6200", "Elevated": "#B3261E", "Inconclusive": "#4A5568"}


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK)
    return {
        "body": base,
        "small": ParagraphStyle("s", parent=base, fontSize=8, leading=11, textColor=MUTED),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                             textColor=NAVY, spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6),
        "cell": ParagraphStyle("c", parent=base, fontSize=8.5, leading=11, alignment=TA_LEFT),
        "banner": ParagraphStyle("bn", parent=base, fontName="Helvetica-Bold", textColor=colors.white, fontSize=10),
    }


def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table(rows, widths, st, header=True):
    data = [[Paragraph(_esc(c), st["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D3DF")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F4F8"))]
    t.setStyle(TableStyle(style))
    return t


def to_pdf(dossier: dict) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    demo = dossier["demonstration"]

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(15 * mm, A4[1] - 9 * mm, "TrustLens AI")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 15 * mm, A4[1] - 9 * mm, f"Evidence dossier {dossier['case']['case_id']}")
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 9 * mm, "Signals, not verdicts. Advisory evidence for an authorised human reviewer.")
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
        if demo:
            canvas.setFillColor(colors.Color(0.9, 0.3, 0.1, alpha=0.10))
            canvas.setFont("Helvetica-Bold", 60)
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "DEMONSTRATION")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=22 * mm, bottomMargin=16 * mm, title=f"TrustLens dossier {dossier['case']['case_id']}")
    W = A4[0] - 30 * mm
    story = []
    c = dossier["case"]
    story.append(Paragraph("Evidence dossier", st["h1"]))
    story.append(Paragraph(f"Generated {_esc(dossier['generated_at'])} by TrustLens AI v{_esc(dossier['generator_version'])}", st["small"]))
    story.append(Spacer(1, 6))
    if demo:
        banner = Table([[Paragraph(_esc(dossier["demonstration_note"]), st["banner"])]], colWidths=[W])
        banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#B4501E")),
                                    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story += [banner, Spacer(1, 6)]
    story.append(_table([["Case ID", c["case_id"], "Status", c["status_label"]],
                         ["Candidate ID", c["candidate_id"], "Session ID", c["session_id"]],
                         ["Created", c["created_at"], "Analysed", c["analysed_at"] or "—"],
                         ["Disputed", "Yes" if c["disputed"] else "No", "", ""]],
                        [W * .17, W * .33, W * .17, W * .33], st, header=False))

    risk = dossier["advisory_risk"]
    story.append(Paragraph("Advisory risk band", st["h2"]))
    if risk:
        band = risk["band"]
        bt = Table([[Paragraph(f"{_esc(band)}", ParagraphStyle("bb", parent=st["banner"], fontSize=14)),
                     Paragraph(f"Aggregated indicator score {risk['score']:.3f} (transparent weighted rules, unvalidated).",
                               ParagraphStyle("bw", parent=st["cell"], textColor=colors.white))]],
                   colWidths=[W * .25, W * .75])
        bt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BAND_COLORS.get(band, "#4A5568"))),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story.append(bt)
        story.append(Spacer(1, 4))
        for r in risk["reasons"]:
            story.append(Paragraph("• " + _esc(r), st["body"]))
        if risk["recapture_recommended"]:
            story.append(Paragraph("<b>Recapture recommended</b> because at least one input was of insufficient quality.", st["body"]))
    else:
        story.append(Paragraph("Checks have not been run.", st["body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Important.</b> {_esc(dossier['confidence_note'])}", st["small"]))

    story.append(Paragraph("Signal summary", st["h2"]))
    rows = [["Signal", "Result", "Quality", "Confidence / measurement", "Method"]]
    for s in dossier["signals"]:
        m = s.get("metrics", {})
        meas = (f"similarity {m['similarity']}" if "similarity" in m else
                (f"{s['confidence']:.2f}" if s.get("confidence") is not None else "not calculated"))
        rows.append([s["name"], RESULT_LABELS[s["result"]], s["quality"], meas, s["method"]])
    story.append(_table(rows, [W * .22, W * .14, W * .1, W * .16, W * .38], st))

    story.append(Paragraph("Evidence by signal", st["h2"]))
    for s in dossier["signals"]:
        block = [Paragraph(f"{_esc(s['name'])} — {RESULT_LABELS[s['result']]}", st["h3"])]
        for e in s["evidence"]:
            block.append(Paragraph("• " + _esc(e), st["body"]))
        if s.get("error"):
            block.append(Paragraph("Error: " + _esc(s["error"]), st["small"]))
        if s.get("findings"):
            frows = [["Check", "Observation", "Severity", "Can indicate", "Cannot establish"]]
            for f in s["findings"]:
                frows.append([f["check"], f["observation"] + (f" ({f['location']})" if f.get("location") else ""),
                              f["severity"], f["means"], f["does_not_mean"]])
            block.append(_table(frows, [W * .14, W * .3, W * .1, W * .23, W * .23], st))
        for name, path in (s.get("artifacts") or {}).items():
            if path and Path(path).exists():
                try:
                    img = RLImage(path)
                    ratio = img.imageHeight / float(img.imageWidth)
                    img.drawWidth, img.drawHeight = W * .5, W * .5 * ratio
                    block += [Spacer(1, 3), Paragraph(_esc(name.replace("_", " ").capitalize()), st["small"]), img]
                except Exception:
                    pass
        if s.get("limitations"):
            block.append(Paragraph("<i>Limitations:</i> " + _esc(" ".join(s["limitations"])), st["small"]))
        block.append(Spacer(1, 4))
        story.append(KeepTogether(block[:6]))
        story.extend(block[6:])

    if dossier["checks_not_completed"]:
        story.append(Paragraph("Checks that could not be completed", st["h2"]))
        story.append(_table([["Signal", "State", "Reason"]] +
                            [[x["signal"], RESULT_LABELS[x["result"]], x["reason"]] for x in dossier["checks_not_completed"]],
                            [W * .3, W * .15, W * .55], st))

    if risk:
        story.append(Paragraph("Suggested next steps for the reviewer", st["h2"]))
        for i, step in enumerate(risk["next_steps"], 1):
            story.append(Paragraph(f"{i}. {_esc(step)}", st["body"]))

    story.append(Paragraph("Human decisions", st["h2"]))
    if dossier["human_decisions"]:
        story.append(_table([["Time", "Reviewer", "Decision", "Notes"]] +
                            [[d["created_at"], d["reviewer_id"], d["decision"], d["notes"]] for d in dossier["human_decisions"]],
                            [W * .2, W * .15, W * .2, W * .45], st))
    else:
        story.append(Paragraph("No human decision has been recorded. The case has no final status.", st["body"]))
    if dossier["appeals"]:
        story.append(Paragraph("Disputes and appeals", st["h2"]))
        story.append(_table([["Time", "Recorded by", "Reason", "Status"]] +
                            [[a["created_at"], a["recorded_by"], a["reason"], a["status"]] for a in dossier["appeals"]],
                            [W * .2, W * .15, W * .5, W * .15], st))

    story.append(Paragraph("Audit trail", st["h2"]))
    story.append(_table([["Time", "Actor", "Event"]] +
                        [[a["created_at"], a["actor"], a["event"]] for a in reversed(dossier["audit_events"])],
                        [W * .3, W * .2, W * .5], st))
    story.append(Spacer(1, 8))
    story.append(Paragraph(_esc(dossier["disclaimer"]), st["small"]))
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()
