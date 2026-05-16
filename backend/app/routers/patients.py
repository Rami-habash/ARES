"""Patient management endpoints.

Admin view   — full list, all profiles, exercise assignment, blank-patient
               creation, doctor-note upload + Nemotron-driven risk profile.
Patient view — own profile only (via patient_link).

All data lives in the single combined DB (claw/data/patients.db).
"""
from __future__ import annotations

import json
import logging
import os
import textwrap
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import get_current_user, require_admin
from app.db.database import get_conn

# Single source of truth — see config.py for the sys.path hook.
from patient_profile.profile import KAGGLE_EXERCISES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["patients"])

NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NEMOTRON_MODEL  = "nvidia/nemotron-3-nano-30b-a3b"

_KAGGLE_SET = set(KAGGLE_EXERCISES)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patient_with_sessions(patient_id: str) -> dict | None:
    with get_conn() as conn:
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

        link = conn.execute(
            "SELECT user_id FROM patient_links WHERE nemo_patient_id = ?",
            (patient_id,),
        ).fetchone()

    risk_profile: dict = {}
    if row["risk_profile_json"]:
        try:
            parsed = json.loads(row["risk_profile_json"])
            if isinstance(parsed, dict):
                risk_profile = parsed
        except json.JSONDecodeError:
            pass

    return {
        "id": row["id"],
        "name": row["name"],
        "date_of_birth": row["date_of_birth"],
        "notes": row["notes"],
        "doctor_note": row["doctor_note"],
        "risk_profile": risk_profile,
        "assigned_exercises": exercises,
        "session_memories": memories,
        "recent_sessions": sessions,
        "alerts": alerts,
        "linked_user_id": link["user_id"] if link else None,
    }


def _all_patient_ids() -> list[str]:
    with get_conn() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM patients ORDER BY id")]


def _refresh_common_exercises_conn(patient_id: str, conn) -> None:
    """Rewrite patient_exercises to the top-3 of patient_exercise_counts.

    Assumes caller already holds (or will commit) a write transaction; the
    caller is responsible for opening/committing. Mirrors the claw helper.
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
            "INSERT OR IGNORE INTO exercises(name) VALUES (?)", (ex_name,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO patient_exercises(patient_id, exercise_id) "
            "SELECT ?, id FROM exercises WHERE name = ?",
            (patient_id, ex_name),
        )


def _sanitize_risk_profile(raw: Any) -> dict:
    """Filter Nemotron's reply against the known catalogs and shape rules."""
    if not isinstance(raw, dict):
        return {"suggested_exercises": [], "risky_exercises": [], "affected_body_parts": []}

    suggested = [e for e in raw.get("suggested_exercises", []) if isinstance(e, str) and e in _KAGGLE_SET]
    risky     = [e for e in raw.get("risky_exercises", [])    if isinstance(e, str) and e in _KAGGLE_SET]

    body_parts: list[dict] = []
    for entry in raw.get("affected_body_parts", []) or []:
        if not isinstance(entry, dict):
            continue
        part = entry.get("part")
        weight = entry.get("weight")
        if not isinstance(part, str) or not part.strip():
            continue
        try:
            weight_f = float(weight)
        except (TypeError, ValueError):
            continue
        weight_f = max(0.1, min(10.0, weight_f))
        body_parts.append({"part": part.strip(), "weight": weight_f})

    return {
        "suggested_exercises": suggested,
        "risky_exercises":     risky,
        "affected_body_parts": body_parts,
    }


_DOCTOR_NOTE_SYSTEM = "detailed thinking off"

def _doctor_note_prompt(note: str) -> str:
    catalog = ", ".join(KAGGLE_EXERCISES)
    return textwrap.dedent(f"""
        A doctor wrote the following note about a rehab patient. Extract a
        structured risk profile.

        Doctor's note:
        \"\"\"{note}\"\"\"

        Return ONLY a JSON object with these three keys (no preamble, no
        explanation, no markdown):

          - "suggested_exercises": list of exercise names from this catalog
            that the patient should start with. Pick names ONLY from:
            {catalog}
          - "risky_exercises": list of exercise names from the same catalog
            that should be flagged as risky for this patient.
          - "affected_body_parts": list of objects of the form
            {{"part": "<body part>", "weight": <float between 0.1 and 10.0>}}.
            Higher weight = more clinically affected.

        Example shape (do NOT copy the exact values):
        {{"suggested_exercises": ["squat"], "risky_exercises": ["deadlift"],
          "affected_body_parts": [{{"part": "knee", "weight": 3.0}}]}}
    """).strip()


async def _call_nemotron_for_note(note: str) -> dict:
    """Ask Nemotron to extract a risk profile. Returns the sanitized dict."""
    empty = {"suggested_exercises": [], "risky_exercises": [], "affected_body_parts": []}
    if not NVIDIA_API_KEY:
        logger.info("doctor-note: NVIDIA_API_KEY not set, returning empty risk profile")
        return empty

    prompt = _doctor_note_prompt(note)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                json={
                    "model": NEMOTRON_MODEL,
                    "messages": [
                        {"role": "system", "content": _DOCTOR_NOTE_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
            )
            data = resp.json()
    except Exception:
        logger.exception("doctor-note: Nemotron call failed")
        return empty

    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        logger.warning("doctor-note: unexpected Nemotron response shape")
        return empty

    # Nemotron sometimes wraps JSON in code fences or prose — find the first {...}.
    import re
    matches = sorted(
        re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL),
        key=len, reverse=True,
    )
    for m in matches:
        try:
            parsed = json.loads(m)
        except json.JSONDecodeError:
            continue
        return _sanitize_risk_profile(parsed)

    logger.warning("doctor-note: no JSON object found in Nemotron reply: %r", content[:200])
    return empty


# ── Schemas ───────────────────────────────────────────────────────────────────

class AssignExercisesRequest(BaseModel):
    exercises: list[str]


class AddMemoryRequest(BaseModel):
    highlight: str


class CreatePatientRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    date_of_birth: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str | None = Field(default=None, max_length=2000)


class DoctorNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=20000)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def list_patients(user: dict = Depends(require_admin)):
    ids = _all_patient_ids()
    if not ids:
        return {"patients": [], "note": "DB not seeded. Run: cd backend && python -m app.db.seed"}
    return {"patients": [_patient_with_sessions(pid) for pid in ids]}


@router.post("", status_code=201)
def create_patient(body: CreatePatientRequest, user: dict = Depends(require_admin)):
    """Create a blank patient row. Linking a login account is a separate step
    via PUT /users/{user_id}/link-patient."""
    new_id = "P" + uuid4().hex[:6].upper()
    with get_conn() as conn:
        # Vanishingly unlikely, but if the hex slice ever collides retry once.
        if conn.execute("SELECT id FROM patients WHERE id = ?", (new_id,)).fetchone():
            new_id = "P" + uuid4().hex[:6].upper()
        conn.execute(
            "INSERT INTO patients(id, name, date_of_birth, notes) VALUES (?, ?, ?, ?)",
            (new_id, body.name, body.date_of_birth, body.notes or ""),
        )
    return {
        "id": new_id,
        "name": body.name,
        "date_of_birth": body.date_of_birth,
        "notes": body.notes or "",
        "doctor_note": None,
        "risk_profile": {},
        "assigned_exercises": [],
        "linked_user_id": None,
    }


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


@router.post("/{patient_id}/doctor-note")
async def upload_doctor_note(
    patient_id: str,
    body: DoctorNoteRequest,
    user: dict = Depends(require_admin),
):
    """Synchronously parse a doctor's note via Nemotron 3 Nano and store the
    resulting risk profile. Suggested exercises seed patient_exercise_counts
    at count=0 so real session data always outranks them."""
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM patients WHERE id = ?", (patient_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Patient not found")

    risk_profile = await _call_nemotron_for_note(body.note)

    with get_conn() as conn:
        conn.execute(
            "UPDATE patients SET doctor_note = ?, risk_profile_json = ? WHERE id = ?",
            (body.note, json.dumps(risk_profile), patient_id),
        )
        for ex_name in risk_profile.get("suggested_exercises", []):
            conn.execute(
                "INSERT OR IGNORE INTO patient_exercise_counts(patient_id, exercise_name, session_count) "
                "VALUES (?, ?, 0)",
                (patient_id, ex_name),
            )
        _refresh_common_exercises_conn(patient_id, conn)

    return {"patient_id": patient_id, "risk_profile": risk_profile}
