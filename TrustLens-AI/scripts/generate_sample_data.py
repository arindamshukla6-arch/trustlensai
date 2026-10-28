"""Regenerate the synthetic demo files in sample_data/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from trustlens.services.sample_data import generate_all  # noqa: E402

for key, path in generate_all(force=True).items():
    print(f"{key:22s} {path}")
