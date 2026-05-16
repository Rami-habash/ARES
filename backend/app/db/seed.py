"""Seed the combined DB with all demo data in one pass.

Clinical data (patients, exercises, prescriptions) and app data (users,
alerts, sessions) all go into the same DB at NemoDemo/data/patients.db.

Usage:
  cd backend && python -m app.db.seed           # safe to re-run (INSERT OR IGNORE)
  cd backend && python -m app.db.seed --reset   # wipe app tables and re-seed

Demo credentials:
  admin@solstice.health / admin1234   (role=admin)
  alice@clinic.com      / patient1234 (role=patient → P001 Alice Nguyen)
  marcus@clinic.com     / patient1234 (role=patient → P002 Marcus Reed)
  priya@clinic.com      / patient1234 (role=patient → P003 Priya Shah)
  diego@clinic.com      / patient1234 (role=patient → P004 Diego Alvarez)
"""
from __future__ import annotations

import json
import sys

from app.core.security import hash_password
from app.db.database import get_conn, init_db

# ── Clinical data ─────────────────────────────────────────────────────────────

KAGGLE_EXERCISES: tuple[str, ...] = (
    "barbell biceps curl", "bench press", "chest fly machine", "deadlift",
    "decline bench press", "hammer curl", "hip thrust", "incline bench press",
    "lat pulldown", "lateral raise", "leg extension", "leg raises", "plank",
    "pull up", "push-up", "romanian deadlift", "russian twist", "shoulder press",
    "squat", "t bar row", "tricep dips", "tricep pushdown",
)

DEMO_PATIENTS = (
    {
        "id": "P001", "name": "Alice Nguyen", "date_of_birth": "1987-04-12",
        "notes": "Post-ACL reconstruction, week 8. Avoid heavy axial load.",
        "exercises": ("squat", "leg extension", "hip thrust", "plank"),
    },
    {
        "id": "P002", "name": "Marcus Reed", "date_of_birth": "1972-11-30",
        "notes": "Rotator cuff repair, week 12. Cleared for light pressing.",
        "exercises": ("shoulder press", "lateral raise", "lat pulldown", "push-up"),
    },
    {
        "id": "P003", "name": "Priya Shah", "date_of_birth": "1995-02-08",
        "notes": "Chronic lower-back pain. Core stability focus.",
        "exercises": ("plank", "russian twist", "romanian deadlift", "hip thrust"),
    },
    {
        "id": "P004", "name": "Diego Alvarez", "date_of_birth": "1960-07-21",
        "notes": "General deconditioning post-hospitalization. Build baseline.",
        "exercises": ("squat", "push-up", "lat pulldown", "leg raises", "plank"),
    },
)

# ── App data ──────────────────────────────────────────────────────────────────

DEMO_USERS = (
    {"email": "admin@solstice.health", "name": "Dr. Admin",    "password": "admin1234",   "role": "admin",   "patient_id": None},
    {"email": "alice@clinic.com",      "name": "Alice Nguyen", "password": "patient1234", "role": "patient", "patient_id": "P001"},
    {"email": "marcus@clinic.com",     "name": "Marcus Reed",  "password": "patient1234", "role": "patient", "patient_id": "P002"},
    {"email": "priya@clinic.com",      "name": "Priya Shah",   "password": "patient1234", "role": "patient", "patient_id": "P003"},
    {"email": "diego@clinic.com",      "name": "Diego Alvarez","password": "patient1234", "role": "patient", "patient_id": "P004"},
)

DEMO_ALERTS = (
    {"patient_id": "P001", "severity": "Warning",  "title": "Knee valgus detected",                  "description": "Right knee valgus exceeded 5° threshold during squat descent.", "metric": "Knee valgus: 8.2°",       "status": "Open"},
    {"patient_id": "P002", "severity": "Warning",  "title": "Compensation in scapular rotation",      "description": "Abnormal scapular winging detected during lateral raise.",     "metric": "Scapular deviation: 12°",  "status": "Open"},
    {"patient_id": "P003", "severity": "Info",     "title": "Form improvement detected",              "description": "Hip alignment improved compared to previous session.",          "metric": "Hip tilt: 3.1°",           "status": "Open"},
    {"patient_id": "P004", "severity": "Critical", "title": "Balance loss risk",                      "description": "Lateral sway exceeded safe threshold during squat.",            "metric": "Lateral sway: 18 cm",      "status": "Open"},
    {"patient_id": "P001", "severity": "Info",     "title": "Session milestone reached",              "description": "Patient completed 50 total reps this session.",                 "metric": "Reps: 50",                 "status": "Dismissed"},
)

DEMO_SESSIONS = (
    {"patient_id": "P001", "session_date": "2024-01-15", "exercises": ["squat", "leg extension", "hip thrust"], "form_score": 76.0, "summary": "Good session. Knee valgus flagged on squat descent. Hip thrust form excellent."},
    {"patient_id": "P002", "session_date": "2024-01-14", "exercises": ["shoulder press", "lateral raise"],       "form_score": 68.0, "summary": "Scapular compensation noted. Recommend reducing load on lateral raise."},
    {"patient_id": "P003", "session_date": "2024-01-15", "exercises": ["plank", "russian twist"],                "form_score": 81.0, "summary": "Core stability improved. Plank hold duration increased by 15s."},
    {"patient_id": "P004", "session_date": "2024-01-15", "exercises": ["squat", "push-up"],                      "form_score": 54.0, "summary": "Balance concern during squat. Recommend supervision for next session."},
)


def seed(reset: bool = False) -> None:
    init_db()  # adds ARES tables to the existing NemoDemo schema

    with get_conn() as conn:
        if reset:
            conn.executescript(
                "DELETE FROM session_logs; DELETE FROM alerts; "
                "DELETE FROM patient_links; DELETE FROM users; "
                "DELETE FROM patient_exercises; DELETE FROM session_memories; "
                "DELETE FROM patients; DELETE FROM exercises;"
            )

        # Clinical data
        conn.executemany(
            "INSERT OR IGNORE INTO exercises(name) VALUES (?)",
            [(name,) for name in KAGGLE_EXERCISES],
        )
        for p in DEMO_PATIENTS:
            conn.execute(
                "INSERT OR IGNORE INTO patients(id, name, date_of_birth, notes) VALUES (?, ?, ?, ?)",
                (p["id"], p["name"], p["date_of_birth"], p["notes"]),
            )
            for ex_name in p["exercises"]:
                conn.execute(
                    "INSERT OR IGNORE INTO patient_exercises(patient_id, exercise_id) "
                    "SELECT ?, id FROM exercises WHERE name = ?",
                    (p["id"], ex_name),
                )

        # App data
        for u in DEMO_USERS:
            cur = conn.execute(
                "INSERT OR IGNORE INTO users(email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                (u["email"], u["name"], hash_password(u["password"]), u["role"]),
            )
            uid = cur.lastrowid or conn.execute(
                "SELECT id FROM users WHERE email = ?", (u["email"],)
            ).fetchone()["id"]
            if u["patient_id"]:
                conn.execute(
                    "INSERT OR IGNORE INTO patient_links(user_id, nemo_patient_id) VALUES (?, ?)",
                    (uid, u["patient_id"]),
                )

        for a in DEMO_ALERTS:
            conn.execute(
                "INSERT OR IGNORE INTO alerts(patient_id, severity, title, description, metric, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (a["patient_id"], a["severity"], a["title"], a["description"], a["metric"], a["status"]),
            )

        for s in DEMO_SESSIONS:
            conn.execute(
                "INSERT OR IGNORE INTO session_logs(patient_id, session_date, exercises_json, form_score, summary) "
                "VALUES (?, ?, ?, ?, ?)",
                (s["patient_id"], s["session_date"], json.dumps(s["exercises"]), s["form_score"], s["summary"]),
            )

    print("Seed complete.")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
