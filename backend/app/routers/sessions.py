"""Session log endpoints.

Session logs record per-session summaries written by the agent after processing
a room video.  Used by both the admin report view and the patient mobile view.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import get_current_user, require_admin
from app.db.database import get_conn

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    patient_id: str
    session_date: str           # YYYY-MM-DD
    exercises: list[str] = []
    form_score: float | None = None
    summary: str = ""


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["exercises"] = json.loads(d.pop("exercises_json", "[]"))
    return d


@router.get("")
def list_sessions(patient_id: str | None = None, user: dict = Depends(get_current_user)):
    """
    Admin: optionally filter by patient_id.
    Patient: always scoped to their own patient_id.
    """
    with get_conn() as conn:
        if user["role"] == "admin":
            if patient_id:
                rows = conn.execute(
                    "SELECT * FROM session_logs WHERE patient_id = ? ORDER BY session_date DESC",
                    (patient_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM session_logs ORDER BY session_date DESC LIMIT 200"
                ).fetchall()
        else:
            link = conn.execute(
                "SELECT nemo_patient_id FROM patient_links WHERE user_id = ?", (user["id"],)
            ).fetchone()
            if link is None:
                return {"sessions": []}
            rows = conn.execute(
                "SELECT * FROM session_logs WHERE patient_id = ? ORDER BY session_date DESC",
                (link["nemo_patient_id"],),
            ).fetchall()

    return {"sessions": [_row_to_dict(r) for r in rows]}


@router.post("", status_code=201)
def create_session(body: CreateSessionRequest, user: dict = Depends(require_admin)):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO session_logs(patient_id, session_date, exercises_json, form_score, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                body.patient_id,
                body.session_date,
                json.dumps(body.exercises),
                body.form_score,
                body.summary,
            ),
        )
        row = conn.execute("SELECT * FROM session_logs WHERE id = ?", (cur.lastrowid,)).fetchone()

    return _row_to_dict(row)


@router.get("/{session_id}")
def get_session(session_id: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM session_logs WHERE id = ?", (session_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    d = _row_to_dict(row)
    # Patients can only read their own sessions
    if user["role"] != "admin":
        with get_conn() as conn:
            link = conn.execute(
                "SELECT nemo_patient_id FROM patient_links WHERE user_id = ?", (user["id"],)
            ).fetchone()
        if link is None or link["nemo_patient_id"] != d["patient_id"]:
            raise HTTPException(status_code=403, detail="Access denied")

    return d
