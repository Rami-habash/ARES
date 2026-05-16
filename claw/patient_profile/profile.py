"""Patient profile store backed by Supabase Postgres.

Schema (created by backend/app/db/database.py:init_db):
  patients(id, name, date_of_birth, notes, doctor_note, risk_profile_json)
  exercises(id, name)                          -- catalog from the Kaggle
                                                  workout-fitness-video dataset
  patient_exercises(patient_id, exercise_id)   -- top-3 *common* exercises view
                                                  (re-computed from counts)
  patient_exercise_counts(patient_id, exercise_name, session_count)
                                               -- raw frequency table; drives
                                                  the top-3 promotion
  session_memories(id, patient_id, created_at, highlight)
                                               -- append-only log of past
                                                  session highlights

Connection handling:
  Prefers the backend's shared psycopg ConnectionPool when available (in-process
  with FastAPI). Falls back to a standalone psycopg.connect() so this module is
  still usable from scripts / pytest sessions that don't import `app.*`.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

# Class names from
# https://www.kaggle.com/datasets/hasyimabdillah/workoutfitness-video
KAGGLE_EXERCISES: tuple[str, ...] = (
    "barbell biceps curl",
    "bench press",
    "chest fly machine",
    "deadlift",
    "decline bench press",
    "hammer curl",
    "hip thrust",
    "incline bench press",
    "lat pulldown",
    "lateral raise",
    "leg extension",
    "leg raises",
    "plank",
    "pull up",
    "push-up",
    "romanian deadlift",
    "russian twist",
    "shoulder press",
    "squat",
    "t bar row",
    "tricep dips",
    "tricep pushdown",
)

# Demo patients. Exercise counts must use names from KAGGLE_EXERCISES.
# These seed `patient_exercise_counts`; `patient_exercises` is then computed
# as the top-3 by count.  Keep in sync with backend/app/db/seed.py.
DEMO_PATIENTS: tuple[dict, ...] = (
    {
        "id": "P001",
        "name": "Alice Nguyen",
        "date_of_birth": "1987-04-12",
        "notes": "Post-ACL reconstruction, week 8. Avoid heavy axial load.",
    },
    {
        "id": "P002",
        "name": "Marcus Reed",
        "date_of_birth": "1972-11-30",
        "notes": "Rotator cuff repair, week 12. Cleared for light pressing.",
    },
    {
        "id": "P003",
        "name": "Priya Shah",
        "date_of_birth": "1995-02-08",
        "notes": "Chronic lower-back pain. Core stability focus.",
    },
    {
        "id": "P004",
        "name": "Diego Alvarez",
        "date_of_birth": "1960-07-21",
        "notes": "General deconditioning post-hospitalization. Build baseline.",
    },
)

DEMO_EXERCISE_COUNTS: dict[str, dict[str, int]] = {
    "P001": {"squat": 10, "hip thrust": 9, "leg extension": 8, "plank": 7},
    "P002": {"shoulder press": 11, "lateral raise": 9, "lat pulldown": 7, "push-up": 5},
    "P003": {"plank": 12, "russian twist": 10, "romanian deadlift": 6, "hip thrust": 4},
    "P004": {"squat": 8, "push-up": 7, "lat pulldown": 6, "leg raises": 5, "plank": 3},
}


@dataclass
class SessionMemory:
    created_at: str
    highlight: str


@dataclass
class PatientProfile:
    id: str
    name: str
    date_of_birth: str
    notes: str
    exercises: list[str]                # top-3 common (from patient_exercises)
    memories: list[SessionMemory]
    doctor_note: str | None = None
    risk_profile: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@contextmanager
def _connect() -> Iterator[psycopg.Connection]:
    """Yield a Postgres connection.

    Prefers the backend's shared pool when `app.db.database` is importable,
    so the FastAPI process doesn't open extra socket connections. Falls back
    to a standalone connect() for scripts and test sessions.
    """
    try:
        from app.db.database import get_conn as _backend_get_conn  # type: ignore
    except Exception:
        _backend_get_conn = None  # type: ignore[assignment]

    if _backend_get_conn is not None:
        with _backend_get_conn() as conn:
            yield conn
        return

    dsn = os.environ.get("ARES_DB_URL", "")
    if not dsn:
        raise RuntimeError(
            "ARES_DB_URL is not set. Set it in your environment or .env file."
        )
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        yield conn


def init_db() -> None:
    """Ensure the clinical + app tables exist.

    Delegates to backend.app.db.database.init_db when available (the canonical
    DDL). Falls back to running just the clinical-side DDL when the backend
    package isn't importable (e.g. running claw standalone).
    """
    try:
        from app.db.database import init_db as _backend_init_db  # type: ignore
        _backend_init_db()
        return
    except Exception:
        pass

    with _connect() as conn:
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
        conn.execute("ALTER TABLE patients ADD COLUMN IF NOT EXISTS doctor_note TEXT;")
        conn.execute("ALTER TABLE patients ADD COLUMN IF NOT EXISTS risk_profile_json TEXT;")


def _refresh_common_exercises(patient_id: str, conn: psycopg.Connection) -> None:
    """Recompute the top-3 common exercises and rewrite patient_exercises.

    Prefers rows with session_count>0 (real session data) over count=0 rows
    (doctor-note seeded but never performed).  If fewer than 3 have count>0,
    fills the remaining slots from count=0 entries so prefetch still has
    something to warm up.
    """
    hot_rows = conn.execute(
        "SELECT exercise_name FROM patient_exercise_counts "
        "WHERE patient_id = %s AND session_count > 0 "
        "ORDER BY session_count DESC, exercise_name ASC LIMIT 3",
        (patient_id,),
    ).fetchall()
    chosen = [r["exercise_name"] for r in hot_rows]

    if len(chosen) < 3:
        cold_rows = conn.execute(
            "SELECT exercise_name FROM patient_exercise_counts "
            "WHERE patient_id = %s AND session_count = 0 "
            "  AND exercise_name NOT IN (SELECT exercise_name FROM patient_exercise_counts "
            "                            WHERE patient_id = %s AND session_count > 0) "
            "ORDER BY exercise_name ASC LIMIT %s",
            (patient_id, patient_id, 3 - len(chosen)),
        ).fetchall()
        chosen.extend(r["exercise_name"] for r in cold_rows)

    conn.execute("DELETE FROM patient_exercises WHERE patient_id = %s", (patient_id,))
    for ex_name in chosen:
        conn.execute(
            "INSERT INTO exercises(name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (ex_name,),
        )
        conn.execute(
            "INSERT INTO patient_exercises(patient_id, exercise_id) "
            "SELECT %s, id FROM exercises WHERE name = %s "
            "ON CONFLICT DO NOTHING",
            (patient_id, ex_name),
        )


def refresh_common_exercises(patient_id: str) -> None:
    """Public wrapper that opens its own connection."""
    with _connect() as conn:
        _refresh_common_exercises(patient_id, conn)


def increment_exercise_count(patient_id: str, exercise_name: str) -> None:
    """Increment the session count for an exercise and refresh top-3."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO patient_exercise_counts(patient_id, exercise_name, session_count) "
            "VALUES (%s, %s, 1) "
            "ON CONFLICT(patient_id, exercise_name) DO UPDATE "
            "SET session_count = patient_exercise_counts.session_count + 1",
            (patient_id, exercise_name),
        )
        _refresh_common_exercises(patient_id, conn)


def seed_db(*, reset: bool = False) -> None:
    init_db()
    with _connect() as conn:
        if reset:
            conn.execute("DELETE FROM patient_exercise_counts;")
            conn.execute("DELETE FROM patient_exercises;")
            conn.execute("DELETE FROM session_memories;")
            conn.execute("DELETE FROM patients;")
            conn.execute("DELETE FROM exercises;")

        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO exercises(name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                [(name,) for name in KAGGLE_EXERCISES],
            )

        for p in DEMO_PATIENTS:
            conn.execute(
                "INSERT INTO patients(id, name, date_of_birth, notes) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (p["id"], p["name"], p["date_of_birth"], p["notes"]),
            )
            counts = DEMO_EXERCISE_COUNTS.get(p["id"], {})
            for ex_name, count in counts.items():
                conn.execute(
                    "INSERT INTO patient_exercise_counts(patient_id, exercise_name, session_count) "
                    "VALUES (%s, %s, %s) ON CONFLICT (patient_id, exercise_name) DO NOTHING",
                    (p["id"], ex_name, count),
                )
            _refresh_common_exercises(p["id"], conn)


def get_patient_profile(patient_id: str) -> PatientProfile | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, date_of_birth, notes, doctor_note, risk_profile_json "
            "FROM patients WHERE id = %s",
            (patient_id,),
        ).fetchone()
        if row is None:
            return None

        exercises = [
            r["name"]
            for r in conn.execute(
                "SELECT e.name FROM exercises e "
                "JOIN patient_exercises pe ON pe.exercise_id = e.id "
                "WHERE pe.patient_id = %s "
                "ORDER BY e.name",
                (patient_id,),
            ).fetchall()
        ]

        memories = [
            SessionMemory(created_at=r["created_at"], highlight=r["highlight"])
            for r in conn.execute(
                "SELECT created_at, highlight FROM session_memories "
                "WHERE patient_id = %s ORDER BY created_at DESC",
                (patient_id,),
            ).fetchall()
        ]

    risk_profile: dict = {}
    if row["risk_profile_json"]:
        try:
            parsed = json.loads(row["risk_profile_json"])
            if isinstance(parsed, dict):
                risk_profile = parsed
        except json.JSONDecodeError:
            pass

    return PatientProfile(
        id=row["id"],
        name=row["name"],
        date_of_birth=row["date_of_birth"],
        notes=row["notes"],
        exercises=exercises,
        memories=memories,
        doctor_note=row["doctor_note"],
        risk_profile=risk_profile,
    )


def add_session_memory(
    patient_id: str,
    highlight: str,
    created_at: str | None = None,
) -> None:
    ts = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO session_memories(patient_id, created_at, highlight) "
            "VALUES (%s, %s, %s)",
            (patient_id, ts, highlight),
        )
