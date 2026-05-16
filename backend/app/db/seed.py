"""Seed the Supabase Postgres DB with all demo data in one pass.

Clinical data (patients, exercises, common-exercise counts) and app data
(users, alerts, sessions) all go into the same Postgres project.

Usage:
  cd backend && python -m app.db.seed           # safe to re-run (ON CONFLICT DO NOTHING)
  cd backend && python -m app.db.seed --reset   # wipe app + clinical tables and re-seed

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

# app.core.config injects claw/ onto sys.path so this import resolves.
from app.core.config import DB_URL  # noqa: F401  (also triggers path setup)
from app.core.security import hash_password
from app.db.database import get_conn, init_db
from patient_profile.profile import (
    KAGGLE_EXERCISES,
    _refresh_common_exercises,
)

# ── Clinical data ─────────────────────────────────────────────────────────────

DEMO_PATIENTS = (
    {"id": "P001", "name": "Alice Nguyen",   "date_of_birth": "1987-04-12",
     "notes": "Post-ACL reconstruction, week 8. Avoid heavy axial load."},
    {"id": "P002", "name": "Marcus Reed",    "date_of_birth": "1972-11-30",
     "notes": "Rotator cuff repair, week 12. Cleared for light pressing."},
    {"id": "P003", "name": "Priya Shah",     "date_of_birth": "1995-02-08",
     "notes": "Chronic lower-back pain. Core stability focus."},
    {"id": "P004", "name": "Diego Alvarez",  "date_of_birth": "1960-07-21",
     "notes": "General deconditioning post-hospitalization. Build baseline."},
)

# Keep in sync with claw/patient_profile/profile.py:DEMO_EXERCISE_COUNTS.
# patient_exercises is derived as top-3 by count.
DEMO_EXERCISE_COUNTS = {
    "P001": {"squat": 10, "hip thrust": 9, "leg extension": 8, "plank": 7},
    "P002": {"shoulder press": 11, "lateral raise": 9, "lat pulldown": 7, "push-up": 5},
    "P003": {"plank": 12, "russian twist": 10, "romanian deadlift": 6, "hip thrust": 4},
    "P004": {"squat": 8, "push-up": 7, "lat pulldown": 6, "leg raises": 5, "plank": 3},
}

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
    init_db()  # creates all tables (clinical + app)

    with get_conn() as conn:
        if reset:
            # Order respects FKs: child tables first.
            for stmt in (
                "DELETE FROM session_logs;",
                "DELETE FROM alerts;",
                "DELETE FROM gym_sessions;",
                "DELETE FROM patient_links;",
                "DELETE FROM users;",
                "DELETE FROM patient_exercise_counts;",
                "DELETE FROM patient_exercises;",
                "DELETE FROM session_memories;",
                "DELETE FROM patients;",
                "DELETE FROM exercises;",
            ):
                conn.execute(stmt)

        # Clinical data
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

        # App data
        for u in DEMO_USERS:
            # Plain ON CONFLICT DO NOTHING wouldn't RETURNING a row on conflict;
            # do a no-op UPDATE so we always get the id back.
            row = conn.execute(
                "INSERT INTO users(email, name, password_hash, role) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email "
                "RETURNING id",
                (u["email"], u["name"], hash_password(u["password"]), u["role"]),
            ).fetchone()
            uid = row["id"]
            if u["patient_id"]:
                conn.execute(
                    "INSERT INTO patient_links(user_id, nemo_patient_id) VALUES (%s, %s) "
                    "ON CONFLICT (user_id) DO UPDATE SET nemo_patient_id = EXCLUDED.nemo_patient_id",
                    (uid, u["patient_id"]),
                )

        for a in DEMO_ALERTS:
            conn.execute(
                "INSERT INTO alerts(patient_id, severity, title, description, metric, status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (a["patient_id"], a["severity"], a["title"], a["description"], a["metric"], a["status"]),
            )

        for s in DEMO_SESSIONS:
            conn.execute(
                "INSERT INTO session_logs(patient_id, session_date, exercises_json, form_score, summary) "
                "VALUES (%s, %s, %s, %s, %s)",
                (s["patient_id"], s["session_date"], json.dumps(s["exercises"]), s["form_score"], s["summary"]),
            )

    print("Seed complete.")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
