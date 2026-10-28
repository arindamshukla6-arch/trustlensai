"""Central configuration. All values can be overridden in a .env file.

IMPORTANT: every weight and threshold below is a prototype default chosen by
hand. None of them has been empirically validated. Before any real-world use
they must be calibrated on representative, consented data and reviewed for
fairness across user groups.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    p = Path(value) if value else default
    if not p.is_absolute():
        p = ROOT_DIR / p
    return p


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: _path("TRUSTLENS_DATA_DIR", ROOT_DIR / "data"))
    models_dir: Path = field(default_factory=lambda: _path("TRUSTLENS_MODELS_DIR", ROOT_DIR / "models"))
    sample_dir: Path = field(default_factory=lambda: ROOT_DIR / "sample_data")
    db_filename: str = field(default_factory=lambda: os.getenv("TRUSTLENS_DB", "trustlens.db"))

    # Access control (prototype-grade: a shared access code, not real auth)
    reviewer_access_code: str = field(default_factory=lambda: os.getenv("REVIEWER_ACCESS_CODE", "change-me"))

    # Privacy
    retention_days: int = field(default_factory=lambda: _i("RETENTION_DAYS", 30))
    max_upload_mb: int = field(default_factory=lambda: _i("MAX_UPLOAD_MB", 50))

    # Risk aggregation (UNVALIDATED prototype defaults)
    weights: dict = field(default_factory=lambda: {
        "face_match": _f("WEIGHT_FACE_MATCH", 0.30),
        "video_replay": _f("WEIGHT_VIDEO_REPLAY", 0.25),
        "challenge_response": _f("WEIGHT_CHALLENGE", 0.15),
        "doc_integrity": _f("WEIGHT_DOC_INTEGRITY", 0.25),
        "doc_metadata": _f("WEIGHT_DOC_METADATA", 0.15),
        "image_forensics": _f("WEIGHT_IMAGE_FORENSICS", 0.35),
        "ai_text": _f("WEIGHT_AI_TEXT", 0.05),
    })
    # Signals that count as "core" evidence. With none of them completed the
    # case is always INCONCLUSIVE.
    critical_signals: tuple = ("face_match", "video_replay", "challenge_response",
                               "doc_integrity", "image_forensics")
    # Weak signals can never push a case above LOW on their own.
    weak_signals: tuple = ("ai_text",)
    weak_signal_cap: float = field(default_factory=lambda: _f("WEAK_SIGNAL_CAP", 0.10))
    moderate_threshold: float = field(default_factory=lambda: _f("THRESHOLD_MODERATE", 0.20))
    elevated_threshold: float = field(default_factory=lambda: _f("THRESHOLD_ELEVATED", 0.45))

    # Face matching (OpenCV SFace cosine threshold published by OpenCV: 0.363)
    face_match_threshold: float = field(default_factory=lambda: _f("FACE_MATCH_THRESHOLD", 0.363))
    face_match_margin: float = field(default_factory=lambda: _f("FACE_MATCH_MARGIN", 0.05))
    min_face_px: int = field(default_factory=lambda: _i("MIN_FACE_PX", 64))

    # Image quality
    min_sharpness: float = field(default_factory=lambda: _f("MIN_SHARPNESS", 40.0))
    min_brightness: float = field(default_factory=lambda: _f("MIN_BRIGHTNESS", 45.0))
    max_brightness: float = field(default_factory=lambda: _f("MAX_BRIGHTNESS", 215.0))

    # Video analysis
    max_video_frames: int = field(default_factory=lambda: _i("MAX_VIDEO_FRAMES", 300))
    min_video_seconds: float = field(default_factory=lambda: _f("MIN_VIDEO_SECONDS", 2.0))
    frozen_diff: float = field(default_factory=lambda: _f("FROZEN_FRAME_DIFF", 0.15))
    frozen_run_seconds: float = field(default_factory=lambda: _f("FROZEN_RUN_SECONDS", 1.5))
    loop_match_diff: float = field(default_factory=lambda: _f("LOOP_MATCH_DIFF", 1.2))
    loop_min_gap_seconds: float = field(default_factory=lambda: _f("LOOP_MIN_GAP_SECONDS", 1.0))
    loop_min_run: int = field(default_factory=lambda: _i("LOOP_MIN_RUN", 6))
    loop_motion_diff: float = field(default_factory=lambda: _f("LOOP_MOTION_DIFF", 6.0))

    # Challenge-response
    challenge_ttl_seconds: int = field(default_factory=lambda: _i("CHALLENGE_TTL_SECONDS", 90))

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def cases_dir(self) -> Path:
        return self.data_dir / "cases"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.cases_dir, self.models_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
