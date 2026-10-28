"""Document integrity screening for PDFs and certificate images.

Produces up to three signals:
* doc_metadata    – PDF metadata consistency (dates, producer, missing fields)
* doc_integrity   – PDF structure: incremental saves, overlays, annotations,
                    scripts, embedded files, signatures, text-layer vs OCR
* image_forensics – for JPEG images: EXIF and Error Level Analysis (ELA)

None of these checks verify a certificate against the issuing institution.
Metadata anomalies are common in legitimate files and are not proof of forgery.
"""
from __future__ import annotations

import io
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import ExifTags, Image
from pypdf import PdfReader
from pypdf.generic import ContentStream, IndirectObject

from ..models import Finding, Quality, Signal, SignalResult

EDITOR_HINTS = ["photoshop", "gimp", "illustrator", "inkscape", "pdfescape", "sejda", "smallpdf",
                "ilovepdf", "pdf-xchange", "foxit phantom", "nitro", "canva", "online pdf editor",
                "paint.net", "pixlr", "word", "libreoffice"]

NOT_VERIFIED = ("This check does not verify the document with the issuing institution. "
                "No issuer database integration exists in this prototype.")


_TESS_CHECKED: Optional[bool] = None


def _tesseract_available() -> bool:
    """True only if pytesseract is importable AND the tesseract binary runs."""
    global _TESS_CHECKED
    if _TESS_CHECKED is not None:
        return _TESS_CHECKED
    try:
        import pytesseract
    except ImportError:
        _TESS_CHECKED = False
        return False
    cmd = os.getenv("TESSERACT_CMD")
    win_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    elif shutil.which("tesseract") is None and win_default.exists():
        pytesseract.pytesseract.tesseract_cmd = str(win_default)
    try:
        pytesseract.get_tesseract_version()
        _TESS_CHECKED = True
    except Exception:
        _TESS_CHECKED = False
    return _TESS_CHECKED


def ocr_image(img: Image.Image) -> Optional[str]:
    if not _tesseract_available():
        return None
    import pytesseract
    try:
        return pytesseract.image_to_string(img)
    except Exception:
        return None


def _parse_pdf_date(value) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if s.startswith("D:"):
        s = s[2:]
    m = re.match(r"(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?", s)
    if not m:
        return None
    y, mo, d, h, mi, se = (int(g) if g else dflt for g, dflt in zip(m.groups()[:6], (0, 1, 1, 0, 0, 0)))
    try:
        dt = datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc)
    except ValueError:
        return None
    sign, oh, om = m.group(7), m.group(8), m.group(9)
    if sign in ("+", "-") and oh:
        from datetime import timedelta
        off = timedelta(hours=int(oh), minutes=int(om or 0))
        dt = dt - off if sign == "+" else dt + off
    return dt


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", text or "")}


# ---------------------------------------------------------------- PDF
def analyse_pdf(path: Path, work_dir: Optional[Path] = None) -> list[Signal]:
    raw = path.read_bytes()
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass
        pages = reader.pages
        _ = len(pages)
    except Exception as e:
        err = f"PDF could not be parsed: {e}"
        return [Signal.failed("doc_metadata", "Document metadata", err),
                Signal.failed("doc_integrity", "Document structure integrity", err)]
    return [_pdf_metadata(reader), _pdf_structure(reader, raw, work_dir)]


def _pdf_metadata(reader: PdfReader) -> Signal:
    key, name = "doc_metadata", "Document metadata"
    method = "pypdf document information dictionary"
    limitations = ["Metadata is easy to edit or strip, and many legitimate tools write odd values.",
                   "Missing metadata is common and is not treated as suspicious.", NOT_VERIFIED]
    try:
        info = reader.metadata or {}
    except Exception as e:
        return Signal.failed(key, name, str(e), method)
    fields = {k.lstrip("/"): str(v) for k, v in dict(info).items()} if info else {}
    created, modified = _parse_pdf_date(fields.get("CreationDate")), _parse_pdf_date(fields.get("ModDate"))
    producer = (fields.get("Producer", "") + " " + fields.get("Creator", "")).strip()
    findings: list[Finding] = []
    if not fields:
        findings.append(Finding("Metadata present", "No document information dictionary", "info",
                                "The producing tool did not write metadata or it was removed.",
                                "Missing metadata is common and not an indicator of forgery."))
    if created and modified:
        if modified < created:
            findings.append(Finding("Date order", f"Modified {modified:%Y-%m-%d %H:%M} is earlier than created {created:%Y-%m-%d %H:%M}",
                                    "medium", "Dates were edited manually or by an unusual tool.",
                                    "Clock errors and some converters also cause this."))
        elif (modified - created).total_seconds() > 3600:
            findings.append(Finding("Edited after creation", f"Modified {(modified - created).days} day(s) after creation",
                                    "low", "The file was saved again after it was first produced.",
                                    "Legitimate re-saves, signing and archiving also update this date."))
    if created and created > datetime.now(timezone.utc):
        findings.append(Finding("Future date", f"Creation date {created:%Y-%m-%d} is in the future", "medium",
                                "Dates were set manually or the clock was wrong.", "Not proof of editing."))
    hits = [h for h in EDITOR_HINTS if h in producer.lower()]
    if hits:
        findings.append(Finding("Producing software", f"Producer/creator mentions: {', '.join(hits)}", "low",
                                "The document passed through general-purpose editing software.",
                                "Institutions also use these tools to produce genuine documents."))
    evidence = [f"{k}: {v}" for k, v in fields.items() if k in
                ("Title", "Producer", "Creator", "CreationDate", "ModDate", "Author", "Keywords")] or ["No metadata fields."]
    sev = max((f.value for f in findings), default=0.0)
    result = SignalResult.CONCERN if sev >= 0.6 else SignalResult.NO_CONCERN
    return Signal(key, name, result, evidence + [f.observation for f in findings if f.severity != "info"],
                  Quality.GOOD, method, limitations, severity=sev if result is SignalResult.CONCERN else 0.0,
                  findings=findings, metrics={"fields": fields})


def _resolve(obj):
    return obj.get_object() if isinstance(obj, IndirectObject) else obj


def _white_fill_rects(page, reader) -> int:
    """Count filled rectangles drawn in pure white — a common way to cover text."""
    try:
        contents = page.get_contents()
        if contents is None:
            return 0
        ops = ContentStream(contents, reader).operations
    except Exception:
        return 0
    count, white, pending_rect = 0, False, False
    for operands, op in ops:
        op = op.decode("latin-1") if isinstance(op, bytes) else str(op)
        if op in ("rg", "g"):
            vals = [float(v) for v in operands]
            white = all(v >= 0.99 for v in vals)
        elif op == "re":
            pending_rect = True
        elif op in ("f", "F", "f*", "B", "b") and pending_rect:
            if white:
                count += 1
            pending_rect = False
        elif op in ("S", "n"):
            pending_rect = False
    return count


def _pdf_structure(reader: PdfReader, raw: bytes, work_dir: Optional[Path]) -> Signal:
    key, name = "doc_integrity", "Document structure integrity"
    method = "pypdf structure inspection; text layer vs OCR comparison (pypdfium2 + Tesseract when installed)"
    limitations = ["Structural indicators show how a file was produced or changed, not whether its content is true.",
                   "Digital signatures are detected but NOT cryptographically validated in this prototype.",
                   "A forger can re-create a document from scratch, leaving no editing traces.", NOT_VERIFIED]
    findings: list[Finding] = []
    metrics: dict = {"pages": len(reader.pages), "bytes": len(raw)}

    eof = raw.count(b"%%EOF")
    metrics["revisions"] = eof
    if eof > 1:
        findings.append(Finding("Incremental updates", f"{eof} saved revisions found in the file", "low",
                                "Content was appended after the original save (editing, form filling or signing).",
                                "Digital signing and form filling legitimately create revisions."))

    root = _resolve(reader.trailer["/Root"])
    names = _resolve(root.get("/Names")) if root.get("/Names") else {}
    if root.get("/OpenAction") or (names and names.get("/JavaScript")):
        findings.append(Finding("Active content", "Document contains an open action or JavaScript", "medium",
                                "Scripts are unusual in certificates and can alter what is displayed.",
                                "Some generators add harmless open actions (e.g. zoom level)."))
    if names and names.get("/EmbeddedFiles"):
        findings.append(Finding("Embedded files", "Document carries attached files", "low",
                                "Unexpected for a certificate.", "Not malicious by itself."))

    sigs = 0
    try:
        for f in (reader.get_fields() or {}).values():
            if f.get("/FT") == "/Sig":
                sigs += 1
    except Exception:
        pass
    metrics["signature_fields"] = sigs
    if sigs:
        findings.append(Finding("Digital signature", f"{sigs} signature field(s) present", "info",
                                "The issuer may have signed the file.",
                                "Presence is not validity: the signature was NOT cryptographically verified."))

    text_pages, annots, white_rects, fonts = [], [], 0, set()
    for i, page in enumerate(reader.pages, start=1):
        try:
            text_pages.append(page.extract_text() or "")
        except Exception:
            text_pages.append("")
        for a in (page.get("/Annots") or []):
            a = _resolve(a)
            st = str(a.get("/Subtype", ""))
            if st in ("/FreeText", "/Stamp", "/Square", "/Ink", "/Caret"):
                annots.append((i, st.lstrip("/")))
        wr = _white_fill_rects(page, reader)
        if wr:
            white_rects += wr
            findings.append(Finding("Covering shapes", f"{wr} white filled rectangle(s) drawn on page {i}", "medium",
                                    "White boxes are a common way to hide original text before typing over it.",
                                    "Designs legitimately use white panels; inspect the page visually.", f"page {i}"))
        try:
            res = _resolve(page.get("/Resources")) or {}
            for fobj in (_resolve(res.get("/Font")) or {}).values():
                fonts.add(str(_resolve(fobj).get("/BaseFont", "?")))
        except Exception:
            pass
        contents = page.get("/Contents")
        if isinstance(_resolve(contents), list) and len(_resolve(contents)) > 1 and eof > 1:
            findings.append(Finding("Appended page content", f"Page {i} has {len(_resolve(contents))} content streams in a multi-revision file",
                                    "medium", "Drawing instructions were added to the page after it was first saved.",
                                    "Signing or stamping workflows can also append content.", f"page {i}"))
    if annots:
        findings.append(Finding("Overlay annotations", "; ".join(f"page {p}: {t}" for p, t in annots[:6]), "medium",
                                "Annotations can place new text or shapes over the original content.",
                                "Reviewers' comments and stamps are also annotations."))
    metrics.update(fonts=sorted(fonts), white_rectangles=white_rects, annotations=len(annots))
    full_text = "\n".join(text_pages)
    metrics["text_excerpt"] = full_text[:1200]
    metrics["text_chars"] = len(full_text)

    # Compare the text layer with what is actually visible (OCR of the rendered page).
    ocr_note = "OCR comparison not run (pypdfium2 or Tesseract not installed)."
    try:
        import pypdfium2 as pdfium
        if _tesseract_available():
            pdf = pdfium.PdfDocument(raw)
            page_img = pdf[0].render(scale=2).to_pil()
            if work_dir:
                p = work_dir / "doc_page1.png"
                page_img.save(p)
                metrics["page_render"] = str(p)
            ocr = ocr_image(page_img) or ""
            layer, seen = _words(text_pages[0] if text_pages else ""), _words(ocr)
            hidden = sorted(layer - seen)
            metrics["ocr_excerpt"] = ocr[:800]
            if layer:
                ratio = len(hidden) / len(layer)
                metrics["text_layer_words_not_visible"] = hidden[:30]
                ocr_note = f"{len(layer) - len(hidden)} of {len(layer)} text-layer words were also found by OCR on page 1."
                if ratio > 0.25 and len(hidden) >= 3:
                    findings.append(Finding("Hidden text", f"{len(hidden)} words exist in the text layer but are not visible: "
                                            f"{', '.join(hidden[:8])}", "medium",
                                            "Original text may be covered or the visible text replaced.",
                                            "OCR misses small, stylised or low-contrast text.", "page 1"))
            elif not full_text.strip():
                ocr_note = "No text layer (likely a scan); OCR text extracted for review."
            pdf.close()
        elif full_text.strip() == "":
            ocr_note = "No text layer and Tesseract is not installed, so no text could be extracted."
    except Exception as e:
        ocr_note = f"OCR comparison failed: {e}"
    metrics["ocr_note"] = ocr_note

    sev = max((f.value for f in findings), default=0.0)
    # Two or more independent medium indicators together are treated as high.
    if sum(1 for f in findings if f.severity == "medium") >= 2:
        sev = 1.0
    result = SignalResult.CONCERN if sev >= 0.6 else SignalResult.NO_CONCERN
    evidence = [f"{metrics['pages']} page(s), {eof} revision(s), {len(fonts)} font(s), {sigs} signature field(s).", ocr_note]
    evidence += [f.observation for f in findings if f.severity != "info"] or ["No structural editing indicators found."]
    return Signal(key, name, result, evidence, Quality.GOOD, method, limitations,
                  severity=sev if result is SignalResult.CONCERN else 0.0, findings=findings, metrics=metrics,
                  artifacts={"page_render": metrics["page_render"]} if metrics.get("page_render") else {})


# ---------------------------------------------------------------- images
GHOST_QUALITIES = (70, 75, 80, 85, 90, 95)
GRID = 32


def jpeg_ghost(img: Image.Image) -> dict:
    """Edge-normalised error-level analysis across several JPEG qualities.

    The image is recompressed at each quality and the luminance error is
    measured on a 32x32 block grid. Because text and edges always produce
    higher error, each block's error is divided by its edge energy and only
    textured blocks are compared with each other. A block whose normalised
    error is a strong outlier (robust z > 4 and at least 0.5 grey levels above
    the median) has a different compression history from its neighbours.
    """
    import cv2
    rgb = img.convert("RGB")
    g = np.asarray(rgb.convert("L")).astype(np.float32)
    lap = np.abs(cv2.Laplacian(g, cv2.CV_32F))
    H, W = g.shape
    gh, gw = max(1, H // GRID), max(1, W // GRID)
    lb = lap[:gh * GRID, :gw * GRID].reshape(GRID, gh, GRID, gw).mean(axis=(1, 3))
    mask = lb > np.percentile(lb, 60)
    best = {"quality": None, "hot": np.empty((0, 2), int), "error": None}
    for q in GHOST_QUALITIES:
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=q)
        buf.seek(0)
        e = np.abs(g - np.asarray(Image.open(buf).convert("L")).astype(np.float32))
        eb = e[:gh * GRID, :gw * GRID].reshape(GRID, gh, GRID, gw).mean(axis=(1, 3))
        r = eb / (lb + 1.0)
        med = float(np.median(r[mask]))
        mad = max(float(np.median(np.abs(r[mask] - med))), 0.1 * med, 1e-4)
        z = (r - med) / (1.4826 * mad)
        hot = np.argwhere(mask & (z > 4.0) & (eb - float(np.median(eb[mask])) > 0.5))
        if best["error"] is None or len(hot) > len(best["hot"]):
            best = {"quality": q, "hot": hot, "error": e}
    return {"quality": best["quality"], "hot": best["hot"], "error": best["error"],
            "block_h": gh, "block_w": gw, "textured_blocks": int(mask.sum())}


def _heatmap(error: np.ndarray, box=None) -> Image.Image:
    from PIL import ImageDraw
    scale = 255.0 / max(1.0, float(np.percentile(error, 99.5)))
    vis = Image.fromarray(np.clip(error * scale, 0, 255).astype(np.uint8)).convert("RGB")
    if box:
        ImageDraw.Draw(vis).rectangle(box, outline=(0, 220, 255), width=4)
    return vis


def analyse_image_document(path: Path, work_dir: Optional[Path] = None) -> list[Signal]:
    key, name = "image_forensics", "Image document forensics (EXIF + error levels)"
    method = "Pillow EXIF inspection; edge-normalised JPEG error-level analysis at qualities 70-95 on a 32x32 grid"
    limitations = ["Error-level analysis highlights regions with a different compression history; it is not proof of editing.",
                   "Re-saving, resizing, screenshots and messaging apps distort or erase these traces.",
                   "Coloured text, stamps and logos can create isolated outliers.", NOT_VERIFIED]
    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        return [Signal.failed(key, name, f"Image could not be opened: {e}", method)]
    findings: list[Finding] = []
    metrics: dict = {"format": img.format, "size": list(img.size)}
    exif = {}
    try:
        exif = {ExifTags.TAGS.get(k, str(k)): str(v)[:120] for k, v in (img.getexif() or {}).items()}
    except Exception:
        pass
    metrics["exif"] = exif
    software = exif.get("Software", "")
    if any(h in software.lower() for h in EDITOR_HINTS):
        findings.append(Finding("Editing software", f"EXIF Software: {software}", "low",
                                "The image was saved by an image editor.", "Scanning apps and printers also use these."))
    text = ocr_image(img)
    metrics["ocr_excerpt"] = (text or "")[:800]
    metrics["ocr_note"] = "OCR text extracted." if text is not None else "Tesseract not installed: no OCR."

    if (img.format or "").upper() != "JPEG":
        evidence = [f"{img.format} image, {img.size[0]}x{img.size[1]}.",
                    "Error-level analysis skipped: it is only meaningful for JPEG images.", metrics["ocr_note"]]
        return [Signal(key, name, SignalResult.INCONCLUSIVE, evidence + [f.observation for f in findings],
                       Quality.UNKNOWN, method, limitations, findings=findings, metrics=metrics)]

    gh_res = jpeg_ghost(img)
    hot, bh, bw = gh_res["hot"], gh_res["block_h"], gh_res["block_w"]
    box = None
    metrics.update(ela_best_quality=gh_res["quality"], ela_outlier_blocks=int(len(hot)),
                   ela_textured_blocks=gh_res["textured_blocks"])
    if len(hot):
        rows, cols = hot[:, 0], hot[:, 1]
        box = (int(cols.min() * bw), int(rows.min() * bh), int((cols.max() + 1) * bw), int((rows.max() + 1) * bh))
        area = (rows.max() - rows.min() + 1) * (cols.max() - cols.min() + 1)
        clustered = area <= 0.15 * GRID * GRID and len(hot) / area >= 0.25
        metrics["ela_region"] = box
        sev = "medium" if len(hot) >= 6 and clustered else "low"
        findings.append(Finding("Compression inconsistency",
                                f"{len(hot)} textured blocks have a different error level from the rest "
                                f"(region x={box[0]}–{box[2]}, y={box[1]}–{box[3]}, strongest at JPEG quality {gh_res['quality']})",
                                sev, "That region may have been pasted in or saved separately from the rest of the image.",
                                "Coloured text, stamps and logos can also stand out; inspect the heatmap and the original.",
                                f"x={box[0]}-{box[2]}, y={box[1]}-{box[3]}"))
    artifacts = {}
    if work_dir:
        p = work_dir / "ela_heatmap.png"
        _heatmap(gh_res["error"], box).save(p)
        artifacts["error_level_heatmap"] = str(p)
    sev_v = max((f.value for f in findings), default=0.0)
    result = SignalResult.CONCERN if sev_v >= 0.6 else SignalResult.NO_CONCERN
    evidence = [f"JPEG {img.size[0]}x{img.size[1]}; {gh_res['textured_blocks']} textured blocks compared.",
                metrics["ocr_note"]] + ([f.observation for f in findings] or ["No localised compression inconsistency found."])
    return [Signal(key, name, result, evidence, Quality.ADEQUATE, method, limitations,
                   severity=sev_v if result is SignalResult.CONCERN else 0.0, findings=findings,
                   metrics=metrics, artifacts=artifacts)]


def analyse(path: Path, work_dir: Optional[Path] = None) -> list[Signal]:
    if path.suffix.lower() == ".pdf":
        return analyse_pdf(path, work_dir)
    return analyse_image_document(path, work_dir)


def extract_text(path: Path) -> str:
    """Text for the statement check: .txt directly, PDFs via the text layer."""
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)
