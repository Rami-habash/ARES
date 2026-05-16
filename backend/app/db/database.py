"""Single Supabase Postgres connection layer for the combined ARES + clinical schema.

All app and clinical tables live in the same Supabase project:
  Clinical: patients, exercises, patient_exercises, session_memories,
            patient_exercise_counts
  App:      users, patient_links, alerts, session_logs, gym_sessions

Connections come from a module-level `psycopg_pool.ConnectionPool`. Callers
use `with get_conn() as conn:` exactly like before — psycopg's context manager
wraps each block in a transaction (commit on clean exit, rollback on raise).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import DB_URL


# Lazy pool — created on first get_conn() call so importing this module is cheap
# (and so tests that monkeypatch DB_URL before first connection work).
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DB_URL,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield a pooled Postgres connection. Transaction commits on clean exit."""
    with _get_pool().connection() as conn:
        yield conn


def close_pool() -> None:
    """Close the pool. Call from lifespan shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def init_db() -> None:
    """Create all ARES + clinical tables. Safe to call repeatedly."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                date_of_birth TEXT,
                notes         TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id   BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_exercises (
                patient_id  TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                exercise_id BIGINT NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                PRIMARY KEY (patient_id, exercise_id)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_memories (
                id         BIGSERIAL PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                highlight  TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_patient
                ON session_memories(patient_id, created_at);
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_exercise_counts (
                patient_id    TEXT    NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                exercise_name TEXT    NOT NULL,
                session_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (patient_id, exercise_name)
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ex_counts_patient
                ON patient_exercise_counts(patient_id, session_count DESC);
        """)

        # Patient extension columns (idempotent in Postgres via IF NOT EXISTS).
        conn.execute("ALTER TABLE patients ADD COLUMN IF NOT EXISTS doctor_note TEXT;")
        conn.execute("ALTER TABLE patients ADD COLUMN IF NOT EXISTS risk_profile_json TEXT;")

        # ── ARES app tables ───────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            BIGSERIAL PRIMARY KEY,
                email         TEXT        NOT NULL UNIQUE,
                name          TEXT        NOT NULL,
                password_hash TEXT,
                role          TEXT        NOT NULL DEFAULT 'patient',
                oauth_sub     TEXT,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_links (
                user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                nemo_patient_id TEXT   NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id          BIGSERIAL PRIMARY KEY,
                patient_id  TEXT        NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                severity    TEXT        NOT NULL DEFAULT 'Warning',
                title       TEXT        NOT NULL,
                description TEXT        NOT NULL,
                metric      TEXT        NOT NULL DEFAULT '',
                status      TEXT        NOT NULL DEFAULT 'Open',
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_logs (
                id             BIGSERIAL PRIMARY KEY,
                patient_id     TEXT             NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                session_date   DATE             NOT NULL DEFAULT current_date,
                exercises_json TEXT             NOT NULL DEFAULT '[]',
                form_score     DOUBLE PRECISION,
                summary        TEXT,
                created_at     TIMESTAMPTZ      NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gym_sessions (
                id          BIGSERIAL PRIMARY KEY,
                patient_id  TEXT        NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                state       TEXT        NOT NULL DEFAULT 'CHECKING_IN',
                started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                ended_at    TIMESTAMPTZ,
                last_event  TEXT,
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_patient
                ON alerts(patient_id, created_at);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_patient
                ON session_logs(patient_id, session_date);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gym_sessions_patient
                ON gym_sessions(patient_id, started_at);
        """)

        # Enable Row-Level Security on every table. The backend connects as
        # the `postgres` superuser, which bypasses RLS — so this is invisible
        # to our code. The point is to make anon / authenticated API keys
        # (PostgREST, Supabase JS) unable to read or write these tables if
        # they ever leak. No policies means "deny all non-superusers".
        for table in (
            "patients", "exercises", "patient_exercises", "session_memories",
            "patient_exercise_counts",
            "users", "patient_links", "alerts", "session_logs", "gym_sessions",
        ):
            conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
