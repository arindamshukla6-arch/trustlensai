"""Download the OpenCV Model Zoo face models (CPU, ~37 MB total).

YuNet face detector  - MIT licence
SFace face recogniser - Apache-2.0 licence
Source: https://github.com/opencv/opencv_zoo
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from trustlens.config import settings  # noqa: E402

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def main() -> int:
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, url in MODELS.items():
        dest = settings.models_dir / name
        if dest.exists() and dest.stat().st_size > 100_000:
            print(f"[skip] {name} already present")
            continue
        print(f"[get ] {name} ...")
        try:
            tmp = dest.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            if tmp.stat().st_size < 100_000 or tmp.read_bytes()[:40].startswith(b"version https://git-lfs"):
                tmp.unlink(missing_ok=True)
                raise RuntimeError("received a Git LFS pointer instead of the model file")
            tmp.replace(dest)
            print(f"[ ok ] {name} {dest.stat().st_size/1e6:.1f} MB sha256={hashlib.sha256(dest.read_bytes()).hexdigest()[:16]}")
        except Exception as e:
            ok = False
            print(f"[fail] {name}: {e}\n       Download it manually from {url}\n       and save it as {dest}")
    print("Done." if ok else "Some models are missing: face matching will show 'Not run'.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
