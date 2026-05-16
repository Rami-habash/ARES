"""Single SQLite DB connection for the combined ARES + NemoDemo schema.

The DB at NemoDemo/data/patients.db already contains:
  patients, exercises, patient_exercises, session_memories

This module adds the ARES-specific tables alongside them:
  users, patient_links, alerts, session_logs

All tables use CREATE TABLE IF NOT EXISTS so existing clinical data is never touched.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.config import DB_PATH


def get_conn(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: Path = DB_PATH) -> None:
    """Add ARES tables to the existing NemoDemo DB. Safe to call repeatedly."""
    with get_conn(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    NOT NULL UNIQUE,
                name          TEXT    NOT NULL,
                password_hash TEXT,
                role          TEXT    NOT NULL DEFAULT 'patient',
                oauth_sub     TEXT,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS patient_links (
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                nemo_patient_id TEXT    NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id  TEXT    NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                severity    TEXT    NOT NULL DEFAULT 'Warning',
                title       TEXT    NOT NULL,
                description TEXT    NOT NULL,
                metric      TEXT    NOT NULL DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'Open',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS session_logs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id     TEXT    NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                session_date   TEXT    NOT NULL DEFAULT (date('now')),
                exercises_json TEXT    NOT NULL DEFAULT '[]',
                form_score     REAL,
                summary        TEXT,
                created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_patient
                ON alerts(patient_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_sessions_patient
                ON session_logs(patient_id, session_date);
        """)
