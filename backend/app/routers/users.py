"""User management endpoints (admin only).

Allows admins to list users, link a user account to a NemoDemo patient record,
and promote/demote roles.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import get_current_user, require_admin
from app.db.database import get_conn

router = APIRouter(prefix="/users", tags=["users"])


class LinkPatientRequest(BaseModel):
    nemo_patient_id: str


class UpdateRoleRequest(BaseModel):
    role: str   # "admin" | "patient"


@router.get("")
def list_users(user: dict = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT u.id, u.email, u.name, u.role, u.created_at, pl.nemo_patient_id "
            "FROM users u LEFT JOIN patient_links pl ON pl.user_id = u.id "
            "ORDER BY u.id"
        ).fetchall()
    # created_at is a datetime; isoformat for JSON.
    out = []
    for r in rows:
        d = dict(r)
        if d.get("created_at") is not None and not isinstance(d["created_at"], str):
            d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return {"users": out}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        link = conn.execute(
            "SELECT nemo_patient_id FROM patient_links WHERE user_id = %s", (user["id"],)
        ).fetchone()
    return {**user, "nemo_patient_id": link["nemo_patient_id"] if link else None}


@router.put("/{user_id}/link-patient")
def link_patient(user_id: int, body: LinkPatientRequest, admin: dict = Depends(require_admin)):
    """Link a user account to a NemoDemo patient record."""
    with get_conn() as conn:
        target = conn.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute(
            "INSERT INTO patient_links(user_id, nemo_patient_id) VALUES (%s, %s) "
            "ON CONFLICT(user_id) DO UPDATE SET nemo_patient_id = EXCLUDED.nemo_patient_id",
            (user_id, body.nemo_patient_id),
        )
    return {"status": "linked", "user_id": user_id, "nemo_patient_id": body.nemo_patient_id}


@router.put("/{user_id}/role")
def update_role(user_id: int, body: UpdateRoleRequest, admin: dict = Depends(require_admin)):
    if body.role not in ("admin", "patient"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'patient'")
    with get_conn() as conn:
        target = conn.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("UPDATE users SET role = %s WHERE id = %s", (body.role, user_id))
    return {"status": "updated", "user_id": user_id, "role": body.role}
