"""Patient management endpoints.

Admin view  — full list, all profiles, exercise assignment
Patient view — own profile only (via patient_link)

All data lives in the single combined DB (NemoDemo/data/patients.db).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import get_current_user, require_admin
from app.db.database import get_conn

router = APIRouter(prefix="/patients", tags=["patients"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patient_with_sessions(patient_id: str) -> dict | None:
    with get_conn() as conn:
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
                "WHERE pe.patient_id = ? ORDER BY e.name",
                (patient_id,),
            )
        ]

        memories = [
            {"created_at": r["created_at"], "highlight": r["highlight"]}
            for r in conn.execute(
                "SELECT created_at, highlight FROM session_memories "
                "WHERE patient_id = ? ORDER BY created_at DESC LIMIT 10",
                (patient_id,),
            )
        ]

        sessions = [
            dict(r)
            for r in conn.execute(
                "SELECT session_date, form_score, summary, exercises_json "
                "FROM session_logs WHERE patient_id = ? ORDER BY session_date DESC LIMIT 5",
                (patient_id,),
            )
        ]
        for s in sessions:
            s["exercises"] = json.loads(s.pop("exercises_json", "[]"))

        alerts = [
            dict(r)
            for r in conn.execute(
                "SELECT id, severity, title, description, metric, status, created_at "
                "FROM alerts WHERE patient_id = ? ORDER BY created_at DESC LIMIT 10",
                (patient_id,),
            )
        ]

    return {
        "id": row["id"],
        "name": row["name"],
        "date_of_birth": row["date_of_birth"],
        "notes": row["notes"],
        "assigned_exercises": exercises,
        "session_memories": memories,
        "recent_sessions": sessions,
        "alerts": alerts,
    }


def _all_patient_ids() -> list[str]:
    with get_conn() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM patients ORDER BY id")]


# ── Schemas ───────────────────────────────────────────────────────────────────

class AssignExercisesRequest(BaseModel):
    exercises: list[str]


class AddMemoryRequest(BaseModel):
    highlight: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def list_patients(user: dict = Depends(require_admin)):
    ids = _all_patient_ids()
    if not ids:
        return {"patients": [], "note": "DB not seeded. Run: cd backend && python -m app.db.seed"}
    return {"patients": [_patient_with_sessions(pid) for pid in ids]}


@router.get("/me")
def my_profile(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        link = conn.execute(
            "SELECT nemo_patient_id FROM patient_links WHERE user_id = ?", (user["id"],)
        ).fetchone()

    if link is None:
        raise HTTPException(status_code=404, detail="No patient profile linked to this account")

    profile = _patient_with_sessions(link["nemo_patient_id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Patient record not found")
    return profile


@router.get("/{patient_id}")
def get_patient(patient_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        with get_conn() as conn:
            link = conn.execute(
                "SELECT nemo_patient_id FROM patient_links WHERE user_id = ?", (user["id"],)
            ).fetchone()
        if link is None or link["nemo_patient_id"] != patient_id:
            raise HTTPException(status_code=403, detail="Access denied")

    profile = _patient_with_sessions(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return profile


@router.put("/{patient_id}/exercises")
def assign_exercises(
    patient_id: str,
    body: AssignExercisesRequest,
    user: dict = Depends(require_admin),
):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM patients WHERE id = ?", (patient_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Patient not found")

        conn.execute("DELETE FROM patient_exercises WHERE patient_id = ?", (patient_id,))
        for ex_name in body.exercises:
            conn.execute(
                "INSERT OR IGNORE INTO patient_exercises(patient_id, exercise_id) "
                "SELECT ?, id FROM exercises WHERE name = ?",
                (patient_id, ex_name),
            )

    return {"status": "updated", "patient_id": patient_id, "exercises": body.exercises}


@router.post("/{patient_id}/memories")
def add_memory(
    patient_id: str,
    body: AddMemoryRequest,
    user: dict = Depends(require_admin),
):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM patients WHERE id = ?", (patient_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Patient not found")
        conn.execute(
            "INSERT INTO session_memories(patient_id, created_at, highlight) "
            "VALUES (?, datetime('now'), ?)",
            (patient_id, body.highlight),
        )
    return {"status": "added"}
