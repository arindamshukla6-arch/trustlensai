"""Generates the SYNTHETIC test files used by demo cases and tests.

Every file is produced from code, contains no real person's data, and is
labelled as synthetic inside the file. Run: python scripts/generate_sample_data.py
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject, TextStringObject
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas

from ..config import settings

INSTITUTION = "Northfield Institute of Technology"
GRADE_POS = (330, 250)  # where the grade line is drawn on the PDF (points)

HUMAN_SOP = """When I was fourteen, the only computer in Ropar's Government Senior Secondary School lab was a
2009 Dell that took six minutes to boot. I spent those minutes reading the manual for Turbo C. In 2022 I
joined a two-month internship at a Mohali logistics startup, where I rewrote their route-planning script and cut
average delivery time from 41 to 33 minutes across 120 daily orders. It was not elegant; my first version crashed
every Friday because I had hard-coded the week length. My mentor, Harpreet, made me write a post-mortem, and that
document taught me more than the fix did. Last year I built a Punjabi-English flashcard app for my grandmother,
who wanted to read her grandson's school notices. Only 37 people use it, but she is one of them. I want to study
human-computer interaction because I keep meeting software that assumes everyone reads English fluently and owns a
fast phone. At your university I hope to work with the accessibility lab on low-bandwidth interfaces. I am not sure
yet whether I want a research career or to start something of my own; I would like the next two years to help me
decide that honestly. I failed my first attempt at the state robotics fair in 2021. Our line follower drifted left
on the polished floor, and we had tested it only on our classroom's rough tiles. We came back in 2023 and placed
fourth out of 58 teams, mostly because we finally tested on the right surface."""

AI_STYLED_SOP = """In today's fast-paced world, technology plays a pivotal role in shaping the future of society.
I am deeply passionate about computer science and its ability to transform lives. Throughout my academic journey,
I have developed a strong foundation in programming and problem solving. Furthermore, I have consistently sought
opportunities to expand my knowledge and skills. Moreover, my experiences have allowed me to navigate the
complexities of the ever-evolving technological landscape. I believe that this program will provide me with the
invaluable opportunity to delve deeper into the realm of artificial intelligence. Additionally, I am eager to
foster meaningful collaborations with peers and faculty members. My unwavering commitment to excellence is a
testament to my dedication and perseverance. I am confident that my holistic approach to learning will enable me
to contribute to the dynamic landscape of innovation. Furthermore, I aspire to leverage cutting-edge tools to
address real-world challenges. Moreover, I believe that education is a journey of continuous growth and discovery.
This program resonates with my values and aspirations, and I am excited to embark on this journey. Additionally,
I hope to seamlessly integrate theory and practice in my future endeavors. In conclusion, I am confident that I
am a strong candidate for this program and that it will help me achieve my goals and make a positive impact."""


def _pdf_date(dt: datetime) -> str:
    return dt.strftime("D:%Y%m%d%H%M%S+00'00'")


def make_certificate_pdf(path: Path, grade: str = "Grade: B") -> None:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    W, H = landscape(A4)
    c.setTitle("Certificate of Completion (SYNTHETIC TEST)")
    c.setAuthor("TrustLens sample generator")
    c.setSubject("Synthetic test document - not a real certificate")
    c.setKeywords("SYNTHETIC TEST FILE")
    c.setStrokeColorRGB(0.05, 0.2, 0.35)
    c.setLineWidth(4)
    c.rect(30, 30, W - 60, H - 60)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(W / 2, H - 110, INSTITUTION)
    c.setFont("Helvetica", 12)
    c.drawCentredString(W / 2, H - 132, "(fictional institution — synthetic test document)")
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(W / 2, H - 190, "Certificate of Completion")
    c.setFont("Helvetica", 14)
    c.drawCentredString(W / 2, H - 240, "This certifies that Test Candidate Alpha")
    c.drawCentredString(W / 2, H - 262, "completed the Bachelor of Technology in Computer Science")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(*GRADE_POS, grade)
    c.setFont("Helvetica", 11)
    c.drawString(80, 90, "Certificate No. NIT-SYN-2024-00417")
    c.drawRightString(W - 80, 90, "Issued 14 June 2024")
    c.setFillColorRGB(0.75, 0.2, 0.1)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(W / 2, 50, "SYNTHETIC TEST FILE — GENERATED FOR TRUSTLENS AI DEMONSTRATION")
    c.showPage()
    c.save()
    reader = PdfReader(io.BytesIO(buf.getvalue()))
    writer = PdfWriter(clone_from=reader)
    created = datetime(2024, 6, 14, 10, 0, tzinfo=timezone.utc)
    writer.add_metadata({"/CreationDate": _pdf_date(created), "/ModDate": _pdf_date(created),
                         "/Producer": "ReportLab (TrustLens synthetic sample)"})
    with open(path, "wb") as fh:
        writer.write(fh)


def make_tampered_pdf(src: Path, dst: Path) -> None:
    """Simulates a typical crude edit: white box over the grade, new grade typed on top,
    saved as an incremental update by an 'online editor' with inconsistent dates."""
    writer = PdfWriter(str(src), incremental=True)
    page = writer.pages[0]
    fonts = page["/Resources"]["/Font"]
    font_name = sorted(fonts.keys())[-1]  # Helvetica-Bold is registered last
    x, y = GRADE_POS
    overlay = DecodedStreamObject()
    overlay.set_data(
        f"q 1 1 1 rg {x - 4} {y - 5} 140 24 re f Q "
        f"BT {font_name} 16 Tf 0 0 0 rg {x} {y} Td (Grade: A+) Tj ET".encode("latin-1"))
    contents = page["/Contents"]
    arr = ArrayObject(contents) if isinstance(contents.get_object(), list) else ArrayObject([contents.indirect_reference or contents])
    arr.append(writer._add_object(overlay))
    page[NameObject("/Contents")] = arr
    writer.add_metadata({"/ModDate": _pdf_date(datetime(2024, 6, 13, 18, 30, tzinfo=timezone.utc)),
                         "/Producer": TextStringObject("Online PDF Editor (TrustLens synthetic tamper test)")})
    with open(dst, "wb") as fh:
        writer.write(fh)


def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _certificate_image(grade: str) -> Image.Image:
    rng = np.random.default_rng(7)
    base = (np.full((800, 1130, 3), 247, np.float32) + rng.normal(0, 3, (800, 1130, 3))).clip(0, 255)
    img = Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(img)
    d.rectangle([25, 25, 1105, 775], outline=(20, 50, 90), width=6)
    d.text((565, 120), INSTITUTION, fill=(20, 40, 70), font=_font(40), anchor="mm")
    d.text((565, 175), "(fictional institution — synthetic scan)", fill=(90, 90, 90), font=_font(20), anchor="mm")
    d.text((565, 270), "Certificate of Completion", fill=(20, 40, 70), font=_font(34), anchor="mm")
    d.text((565, 360), "Test Candidate Beta", fill=(10, 10, 10), font=_font(30), anchor="mm")
    d.text((565, 470), grade, fill=(10, 10, 10), font=_font(30), anchor="mm")
    d.text((565, 740), "SYNTHETIC TEST FILE", fill=(180, 60, 30), font=_font(18), anchor="mm")
    return img.filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(0.6))


def make_certificate_images(genuine: Path, tampered: Path) -> None:
    _certificate_image("Grade: B").save(genuine, "JPEG", quality=80)
    # Tamper: open the already-compressed scan, paste a freshly rendered (never-compressed)
    # region with a different grade, and save again.
    scan = Image.open(genuine).convert("RGB")
    patch = _certificate_image("Grade: A+").crop((420, 440, 710, 500))
    scan.paste(patch, (420, 440))
    scan.save(tampered, "JPEG", quality=95)


def _scene(t: float, w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    frame = np.zeros((h, w, 3), np.float32)
    frame[..., 0] = 90 + 40 * np.sin(xx / 70 + t)
    frame[..., 1] = 100 + 40 * np.sin(yy / 50 - t * 0.7)
    frame[..., 2] = 120 + 30 * np.cos((xx + yy) / 90 + t * 0.5)
    cx, cy = int(w / 2 + w / 4 * np.sin(t * 1.3)), int(h / 2 + h / 5 * np.cos(t))
    cv2.circle(frame, (cx, cy), 60, (200, 210, 230), -1)
    cv2.rectangle(frame, (int(50 + 30 * t) % (w - 80), 40), (int(50 + 30 * t) % (w - 80) + 70, 110), (40, 60, 160), -1)
    return frame


def _write_video(path: Path, frames: list[np.ndarray], fps: int) -> None:
    h, w = frames[0].shape[:2]
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not out.isOpened():
        raise RuntimeError("OpenCV could not create an mp4 writer on this system.")
    for f in frames:
        out.write(np.clip(f, 0, 255).astype(np.uint8))
    out.release()


def make_videos(motion: Path, replay: Path, poor: Path) -> None:
    rng = np.random.default_rng(1)
    fps, w, h = 20, 640, 480
    # Continuous synthetic motion + sensor-like noise (no repeats).
    _write_video(motion, [_scene(i / fps, w, h) + rng.normal(0, 4, (h, w, 3)) for i in range(fps * 6)], fps)
    # A 2-second clip played three times in a row: a replay loop.
    clip = [_scene(i / fps, w, h) + rng.normal(0, 4, (h, w, 3)) for i in range(fps * 2)]
    _write_video(replay, clip * 3, fps)
    # Dark, blurry, low-resolution, short.
    small = [cv2.GaussianBlur(cv2.resize(_scene(i / 10, w, h) * 0.15, (176, 144)), (9, 9), 4)
             + rng.normal(0, 1, (144, 176, 3)) for i in range(15)]
    _write_video(poor, small, 10)


FILES = {
    "genuine_certificate": "synthetic_genuine_certificate.pdf",
    "tampered_certificate": "synthetic_tampered_certificate.pdf",
    "genuine_scan": "synthetic_genuine_certificate_scan.jpg",
    "tampered_scan": "synthetic_tampered_certificate_scan.jpg",
    "motion_video": "synthetic_continuous_motion.mp4",
    "replay_video": "synthetic_replayed_loop.mp4",
    "poor_video": "synthetic_poor_quality.mp4",
    "human_sop": "synthetic_statement_specific.txt",
    "ai_sop": "synthetic_statement_generic.txt",
}


def path_for(key: str, folder: Path | None = None) -> Path:
    return (folder or settings.sample_dir) / FILES[key]


def generate_all(folder: Path | None = None, force: bool = False) -> dict[str, Path]:
    folder = folder or settings.sample_dir
    folder.mkdir(parents=True, exist_ok=True)
    p = {k: folder / v for k, v in FILES.items()}
    if force or not all(x.exists() for x in p.values()):
        make_certificate_pdf(p["genuine_certificate"])
        make_tampered_pdf(p["genuine_certificate"], p["tampered_certificate"])
        make_certificate_images(p["genuine_scan"], p["tampered_scan"])
        make_videos(p["motion_video"], p["replay_video"], p["poor_video"])
        p["human_sop"].write_text(HUMAN_SOP.replace("\n", " "), encoding="utf-8")
        p["ai_sop"].write_text(AI_STYLED_SOP.replace("\n", " "), encoding="utf-8")
        (folder / "README_SYNTHETIC.txt").write_text(
            "All files in this folder are SYNTHETIC test data generated by code for the TrustLens AI demo.\n"
            "They contain no real person's data. 'tampered' and 'replayed' files were deliberately manipulated\n"
            "to exercise the checks. No real face images are included: use consented photos of your own team\n"
            "to demonstrate face matching.\n", encoding="utf-8")
    return p
