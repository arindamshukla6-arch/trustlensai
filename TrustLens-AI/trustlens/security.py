"""Upload validation, safe storage and simple access control."""
from __future__ import annotations

import hashlib
import hmac
import io
import re
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import settings

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".webm", ".mkv"}
PDF_EXTS = {".pdf"}
TEXT_EXTS = {".txt"}

KIND_EXTS = {
    "reference_image": IMAGE_EXTS,
    "capture_image": IMAGE_EXTS,
    "capture_video": VIDEO_EXTS,
    "document": PDF_EXTS | IMAGE_EXTS,
    "statement": TEXT_EXTS | PDF_EXTS,
    "challenge_baseline": IMAGE_EXTS,
    "challenge_response": IMAGE_EXTS,
}


class UploadError(ValueError):
    pass


@dataclass
class StoredFile:
    kind: str
    path: Path
    ext: str
    sha256: str
    size: int


def safe_ext(filename: str) -> str:
    """Return a lower-case extension from an untrusted filename, or ''."""
    name = Path(str(filename).replace("\\", "/")).name
    m = re.search(r"(\.[A-Za-z0-9]{1,5})$", name)
    return m.group(1).lower() if m else ""


def sniff(data: bytes, ext: str) -> bool:
    """Check the file content really matches the claimed type."""
    if ext in PDF_EXTS:
        return data[:1024].lstrip().startswith(b"%PDF-")
    if ext in IMAGE_EXTS:
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            return True
        except Exception:
            return False
    if ext in TEXT_EXTS:
        try:
            data.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    if ext in VIDEO_EXTS:
        head = data[:64]
        return (b"ftyp" in head[:12] or head.startswith(b"RIFF") or
                head.startswith(b"\x1a\x45\xdf\xa3"))  # mp4/mov, avi, webm/mkv
    return False


def is_valid_case_id(case_id: str) -> bool:
    return bool(re.fullmatch(r"TL-[0-9A-F]{10}", case_id or ""))


def case_dir(case_id: str) -> Path:
    if not is_valid_case_id(case_id):
        raise UploadError("Invalid case ID.")
    d = (settings.cases_dir / case_id).resolve()
    if settings.cases_dir.resolve() not in d.parents:
        raise UploadError("Invalid case path.")
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_upload(case_id: str, kind: str, filename: str, data: bytes) -> StoredFile:
    """Validate and store an upload under a random server-side name.

    The original filename is never used on disk and is not persisted.
    """
    if kind not in KIND_EXTS:
        raise UploadError(f"Unknown upload type: {kind}")
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise UploadError(f"The file is larger than {settings.max_upload_mb} MB.")
    ext = safe_ext(filename)
    if ext not in KIND_EXTS[kind]:
        allowed = ", ".join(sorted(KIND_EXTS[kind]))
        raise UploadError(f"'{ext or 'no extension'}' is not accepted here. Use: {allowed}.")
    if not sniff(data, ext):
        raise UploadError("The file content does not match its extension.")
    path = case_dir(case_id) / f"{kind}_{uuid.uuid4().hex[:12]}{ext}"
    path.write_bytes(data)
    return StoredFile(kind, path, ext, hashlib.sha256(data).hexdigest(), len(data))


def check_access_code(code: str) -> bool:
    expected = settings.reviewer_access_code or ""
    return bool(code) and hmac.compare_digest(code.encode(), expected.encode())


def valid_reviewer_id(rid: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{2,40}", rid or ""))


def new_case_id() -> str:
    return "TL-" + secrets.token_hex(5).upper()


def mask(value: str, keep: int = 2) -> str:
    """Mask an identifier for display in shared views."""
    if not value:
        return ""
    return value[:keep] + "•" * max(3, len(value) - keep)
