"""Patient profile store backed by SQLite.

Schema:
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
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
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

            CREATE TABLE IF NOT EXISTS patient_exercise_counts (
                patient_id    TEXT    NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                exercise_name TEXT    NOT NULL,
                session_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (patient_id, exercise_name)
            );

            CREATE INDEX IF NOT EXISTS idx_ex_counts_patient
                ON patient_exercise_counts(patient_id, session_count DESC);
            """
        )

        # ALTER TABLE is not idempotent inside executescript (the script aborts
        # on first error). Run each one in its own try/except so re-running
        # init_db on a populated DB is safe.
        for stmt in (
            "ALTER TABLE patients ADD COLUMN doctor_note TEXT",
            "ALTER TABLE patients ADD COLUMN risk_profile_json TEXT",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists


def _refresh_common_exercises(patient_id: str, conn: sqlite3.Connection) -> None:
    """Recompute the top-3 common exercises and rewrite patient_exercises.

    Prefers rows with session_count>0 (real session data) over count=0 rows
    (doctor-note seeded but never performed).  If fewer than 3 have count>0,
    fills the remaining slots from count=0 entries so prefetch still has
    something to warm up.
    """
    hot = conn.execute(
        "SELECT exercise_name FROM patient_exercise_counts "
        "WHERE patient_id = ? AND session_count > 0 "
        "ORDER BY session_count DESC, exercise_name ASC LIMIT 3",
        (patient_id,),
    ).fetchall()
    chosen = [r["exercise_name"] for r in hot]

    if len(chosen) < 3:
        cold = conn.execute(
            "SELECT exercise_name FROM patient_exercise_counts "
            "WHERE patient_id = ? AND session_count = 0 "
            "  AND exercise_name NOT IN (SELECT exercise_name FROM patient_exercise_counts "
            "                            WHERE patient_id = ? AND session_count > 0) "
            "ORDER BY exercise_name ASC LIMIT ?",
            (patient_id, patient_id, 3 - len(chosen)),
        ).fetchall()
        chosen.extend(r["exercise_name"] for r in cold)

    conn.execute("DELETE FROM patient_exercises WHERE patient_id = ?", (patient_id,))
    for ex_name in chosen:
        conn.execute(
            "INSERT OR IGNORE INTO exercises(name) VALUES (?)",
            (ex_name,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO patient_exercises(patient_id, exercise_id) "
            "SELECT ?, id FROM exercises WHERE name = ?",
            (patient_id, ex_name),
        )


def refresh_common_exercises(patient_id: str, db_path: Path = DB_PATH) -> None:
    """Public wrapper that opens its own write-locked connection."""
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _refresh_common_exercises(patient_id, conn)


def increment_exercise_count(
    patient_id: str, exercise_name: str, db_path: Path = DB_PATH
) -> None:
    """Increment the session count for an exercise and refresh top-3.

    Wrapped in BEGIN IMMEDIATE so concurrent daemon ticks don't race on the
    top-3 refresh (the daemon emits PATIENT_PAUSED on a fast cadence).
    """
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO patient_exercise_counts(patient_id, exercise_name, session_count) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(patient_id, exercise_name) DO UPDATE "
            "SET session_count = session_count + 1",
            (patient_id, exercise_name),
        )
        _refresh_common_exercises(patient_id, conn)


def seed_db(db_path: Path = DB_PATH, *, reset: bool = False) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        if reset:
            conn.executescript(
                "DELETE FROM patient_exercise_counts;"
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
            counts = DEMO_EXERCISE_COUNTS.get(p["id"], {})
            for ex_name, count in counts.items():
                conn.execute(
                    "INSERT OR IGNORE INTO patient_exercise_counts(patient_id, exercise_name, session_count) "
                    "VALUES (?, ?, ?)",
                    (p["id"], ex_name, count),
                )
            _refresh_common_exercises(p["id"], conn)


def get_patient_profile(
    patient_id: str, db_path: Path = DB_PATH
) -> PatientProfile | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, date_of_birth, notes, doctor_note, risk_profile_json "
            "FROM patients WHERE id = ?",
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
