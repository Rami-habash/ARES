"""Test fixtures.

The key trick: ARES_DB_PATH MUST be set in the environment BEFORE any
`app.*` module is imported, because `app/core/config.py` reads it at import
time. We force-reimport any cached `app.*` modules per fixture to make this
deterministic across multiple tests in the same session.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make repo root importable so `claw` and `app` both resolve.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_REPO_ROOT = _BACKEND.parent
if str(_REPO_ROOT / "claw") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "claw"))


def _purge_app_modules() -> None:
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Fresh FastAPI TestClient pointed at a temp SQLite DB."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("ARES_DB_PATH", str(db_file))

    _purge_app_modules()
    from app.db.database import init_db
    from app.db.seed import seed
    from app.main import app
    from fastapi.testclient import TestClient

    init_db(db_file)
    seed()
    return TestClient(app)


@pytest.fixture
def admin_token(test_app):
    resp = test_app.post(
        "/auth/login",
        json={"email": "admin@solstice.health", "password": "admin1234"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def patient_token(test_app):
    resp = test_app.post(
        "/auth/login",
        json={"email": "alice@clinic.com", "password": "patient1234"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def patient_headers(patient_token):
    return {"Authorization": f"Bearer {patient_token}"}
