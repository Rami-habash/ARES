"""Test fixtures for the Supabase Postgres-backed backend.

Strategy
────────
Tests target a *dedicated* Supabase project (or any Postgres database) via the
``ARES_TEST_DB_URL`` env var. To keep tests isolated and fast, each test runs
on a single shared connection wrapped in a transaction that is rolled back at
teardown, so every test starts from a clean snapshot of the seeded data.

If ``ARES_TEST_DB_URL`` is not set, the whole suite is skipped — never run
tests against a production / shared dev DB.

How it works
────────────
1. Session-scoped: drop all tables (clean slate), then call ``init_db()`` +
   ``seed()`` so demo data is committed to the test DB.
2. Per-function: open a fresh psycopg connection, wrap the test in a
   ``force_rollback`` transaction, monkeypatch ``app.db.database._pool`` so
   every call to ``get_conn()`` re-uses the test's connection. The test sees
   the committed seed data; everything it writes vanishes at teardown.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg.rows import dict_row

# Make repo root importable so `claw` and `app` both resolve.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_REPO_ROOT = _BACKEND.parent
if str(_REPO_ROOT / "claw") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "claw"))

_TEST_DB_URL = os.environ.get("ARES_TEST_DB_URL", "")


def _purge_app_modules() -> None:
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]


@pytest.fixture(scope="session")
def _seeded_db() -> Iterator[None]:
    """Initialize schema and seed data exactly once for the test session."""
    if not _TEST_DB_URL:
        pytest.skip(
            "ARES_TEST_DB_URL is not set; configure a dedicated Supabase test "
            "project URL to run integration tests. See backend/SUPABASE_SETUP.md."
        )

    # Make sure app.* picks up our test URL on (re)import.
    os.environ["ARES_DB_URL"] = _TEST_DB_URL
    _purge_app_modules()

    # Wipe to guarantee a clean schema state across runs.
    with psycopg.connect(_TEST_DB_URL, row_factory=dict_row) as wipe_conn:
        for stmt in (
            "DROP TABLE IF EXISTS session_logs CASCADE;",
            "DROP TABLE IF EXISTS alerts CASCADE;",
            "DROP TABLE IF EXISTS gym_sessions CASCADE;",
            "DROP TABLE IF EXISTS patient_links CASCADE;",
            "DROP TABLE IF EXISTS users CASCADE;",
            "DROP TABLE IF EXISTS patient_exercise_counts CASCADE;",
            "DROP TABLE IF EXISTS patient_exercises CASCADE;",
            "DROP TABLE IF EXISTS session_memories CASCADE;",
            "DROP TABLE IF EXISTS exercises CASCADE;",
            "DROP TABLE IF EXISTS patients CASCADE;",
        ):
            wipe_conn.execute(stmt)
        wipe_conn.commit()

    from app.db.database import init_db, close_pool  # noqa: WPS433
    from app.db.seed import seed                      # noqa: WPS433

    init_db()
    seed()
    close_pool()  # release the seed-time pool; per-test fixtures own their conn

    yield


class _SingleConnPool:
    """Pool-shaped object that always hands out the SAME connection.

    Used so every ``get_conn()`` call in the app code joins the same
    transaction as the test fixture. Inside the per-call ``connection()`` we
    open a savepoint so handlers that raise rollback only their own work,
    while handlers that succeed leave their writes visible to later requests
    within the same test.
    """

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    @contextmanager
    def connection(self):
        with self._conn.transaction():
            yield self._conn

    def close(self) -> None:  # called by app.db.database.close_pool() on shutdown
        pass


@pytest.fixture
def db_conn(_seeded_db) -> Iterator[psycopg.Connection]:
    """Per-test connection wrapped in a force-rolled-back outer transaction."""
    conn = psycopg.connect(_TEST_DB_URL, row_factory=dict_row, autocommit=False)
    try:
        with conn.transaction(force_rollback=True):
            yield conn
    finally:
        conn.close()


@pytest.fixture
def test_app(db_conn, monkeypatch):
    """Fresh FastAPI TestClient routed through the rolled-back connection."""
    _purge_app_modules()

    from app.db import database as db_module  # noqa: WPS433

    # Replace the lazy pool BEFORE the app imports so request handlers share
    # the test transaction. _get_pool() will return our single-conn pool.
    monkeypatch.setattr(db_module, "_pool", _SingleConnPool(db_conn))

    from app.main import app                  # noqa: WPS433
    from fastapi.testclient import TestClient

    # Skip the lifespan (it would call init_db/seed again and try to use the
    # real ConnectionPool); TestClient as a plain context manager still works
    # for non-lifespan-dependent routes.
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
