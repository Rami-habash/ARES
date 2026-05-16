"""Patient profile store backed by SQLite.

Schema:
  patients(id, name, date_of_birth, notes)
  exercises(id, name)                          -- catalog from the Kaggle
                                                  workout-fitness-video dataset
  patient_exercises(patient_id, exercise_id)   -- doctor's prescription
  session_memories(id, patient_id, created_at, highlight)
                                               -- append-only log of past
                                                  session highlights
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "patients.db"

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

# Demo patients. Exercise names must appear in KAGGLE_EXERCISES.
DEMO_PATIENTS: tuple[dict, ...] = (
    {
        "id": "P001",
        "name": "Alice Nguyen",
        "date_of_birth": "1987-04-12",
        "notes": "Post-ACL reconstruction, week 8. Avoid heavy axial load.",
        "exercises": ("squat", "leg extension", "hip thrust", "plank"),
    },
    {
        "id": "P002",
        "name": "Marcus Reed",
        "date_of_birth": "1972-11-30",
        "notes": "Rotator cuff repair, week 12. Cleared for light pressing.",
        "exercises": (
            "shoulder press",
            "lateral raise",
            "lat pulldown",
            "push-up",
        ),
    },
    {
        "id": "P003",
        "name": "Priya Shah",
        "date_of_birth": "1995-02-08",
        "notes": "Chronic lower-back pain. Core stability focus.",
        "exercises": ("plank", "russian twist", "romanian deadlift", "hip thrust"),
    },
    {
        "id": "P004",
        "name": "Diego Alvarez",
        "date_of_birth": "1960-07-21",
        "notes": "General deconditioning post-hospitalization. Build baseline.",
        "exercises": ("squat", "push-up", "lat pulldown", "leg raises", "plank"),
    },
)


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
    exercises: list[str]
    memories: list[SessionMemory]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                date_of_birth TEXT,
                notes         TEXT
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS patient_exercises (
                patient_id  TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                PRIMARY KEY (patient_id, exercise_id)
            );

            CREATE TABLE IF NOT EXISTS session_memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                highlight  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_patient
                ON session_memories(patient_id, created_at);
            """
        )


def seed_db(db_path: Path = DB_PATH, *, reset: bool = False) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        if reset:
            conn.executescript(
                "DELETE FROM patient_exercises;"
                "DELETE FROM session_memories;"
                "DELETE FROM patients;"
                "DELETE FROM exercises;"
            )

        conn.executemany(
            "INSERT OR IGNORE INTO exercises(name) VALUES (?)",
            [(name,) for name in KAGGLE_EXERCISES],
        )

        for p in DEMO_PATIENTS:
            conn.execute(
                "INSERT OR IGNORE INTO patients(id, name, date_of_birth, notes) "
                "VALUES (?, ?, ?, ?)",
                (p["id"], p["name"], p["date_of_birth"], p["notes"]),
            )
            for ex_name in p["exercises"]:
                conn.execute(
                    "INSERT OR IGNORE INTO patient_exercises(patient_id, exercise_id) "
                    "SELECT ?, id FROM exercises WHERE name = ?",
                    (p["id"], ex_name),
                )


def get_patient_profile(
    patient_id: str, db_path: Path = DB_PATH
) -> PatientProfile | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, date_of_birth, notes FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
        if row is None:
            return None

        exercises = [
            r["name"]
            for r in conn.execute(
                "SELECT e.name FROM exercises e "
                "JOIN patient_exercises pe ON pe.exercise_id = e.id "
                "WHERE pe.patient_id = ? "
                "ORDER BY e.name",
                (patient_id,),
            )
        ]

        memories = [
            SessionMemory(created_at=r["created_at"], highlight=r["highlight"])
            for r in conn.execute(
                "SELECT created_at, highlight FROM session_memories "
                "WHERE patient_id = ? ORDER BY created_at DESC",
                (patient_id,),
            )
        ]

    return PatientProfile(
        id=row["id"],
        name=row["name"],
        date_of_birth=row["date_of_birth"],
        notes=row["notes"],
        exercises=exercises,
        memories=memories,
    )


def add_session_memory(
    patient_id: str,
    highlight: str,
    db_path: Path = DB_PATH,
    created_at: str | None = None,
) -> None:
    ts = created_at or datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO session_memories(patient_id, created_at, highlight) "
            "VALUES (?, ?, ?)",
            (patient_id, ts, highlight),
        )