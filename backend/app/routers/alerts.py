"""Alert management endpoints.

Alerts are written by the CV pipeline / agent layer when a movement event is
flagged.  Admins see all alerts; patients see only their own.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import get_current_user, require_admin
from app.db.database import get_conn

router = APIRouter(prefix="/alerts", tags=["alerts"])


class CreateAlertRequest(BaseModel):
    patient_id: str
    severity: str = "Warning"   # Critical | Warning | Info
    title: str
    description: str
    metric: str = ""


class UpdateAlertRequest(BaseModel):
    status: str   # Open | Dismissed | Escalated


def _row_to_dict(row) -> dict:
    d = dict(row)
    # Rename created_at → timestamp to match frontend Alert type.
    # Postgres returns a datetime; isoformat for JSON.
    ts = d.pop("created_at")
    if isinstance(ts, datetime):
        ts = ts.isoformat()
    d["timestamp"] = ts
    # Add patient_name stub (full name lookup handled by frontend or agent)
    d.setdefault("patient_name", d["patient_id"])
    return d


@router.get("")
def list_alerts(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        if user["role"] == "admin":
            rows = conn.execute(
                "SELECT id, patient_id, severity, title, description, metric, status, created_at "
                "FROM alerts ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        else:
            # Patient: only their own alerts via patient_link
            link = conn.execute(
                "SELECT nemo_patient_id FROM patient_links WHERE user_id = %s", (user["id"],)
            ).fetchone()
            if link is None:
                return {"alerts": []}
            rows = conn.execute(
                "SELECT id, patient_id, severity, title, description, metric, status, created_at "
                "FROM alerts WHERE patient_id = %s ORDER BY created_at DESC LIMIT 50",
                (link["nemo_patient_id"],),
            ).fetchall()

    return {"alerts": [_row_to_dict(r) for r in rows]}


@router.post("", status_code=201)
def create_alert(body: CreateAlertRequest, user: dict = Depends(require_admin)):
    """Admin / agent layer — create a new alert."""
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO alerts(patient_id, severity, title, description, metric) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, patient_id, severity, title, description, metric, status, created_at",
            (body.patient_id, body.severity, body.title, body.description, body.metric),
        ).fetchone()

    return _row_to_dict(row)


@router.patch("/{alert_id}")
def update_alert(alert_id: int, body: UpdateAlertRequest, user: dict = Depends(require_admin)):
    allowed = {"Open", "Dismissed", "Escalated"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")

    with get_conn() as conn:
        row = conn.execute(
            "UPDATE alerts SET status = %s WHERE id = %s "
            "RETURNING id, patient_id, severity, title, description, metric, status, created_at",
            (body.status, alert_id),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _row_to_dict(row)


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: int, user: dict = Depends(require_admin)):
    with get_conn() as conn:
        conn.execute("DELETE FROM alerts WHERE id = %s", (alert_id,))
