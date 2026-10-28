import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Every test gets its own empty database and case folder."""
    from trustlens.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "reviewer_access_code", "test-code")
    from trustlens import database
    database.init_db()
    yield


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    from trustlens.services.sample_data import generate_all
    return generate_all(tmp_path_factory.mktemp("samples"), force=True)
