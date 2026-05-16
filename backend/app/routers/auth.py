"""Authentication routes.

Email/password flow
────────────────────
POST /auth/register   — create a new account (role=patient by default)
POST /auth/login      — returns access token

Google OAuth flow
─────────────────
GET  /auth/google          — redirect to Google consent screen
GET  /auth/google/callback — exchange code → token, upsert user, return JWT

The Google flow requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the env.
For the demo, email/password is fully functional without any Google credentials.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.core.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_conn

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "patient"       # "patient" or "admin" — production should validate this further


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    user_id: int


# ── Email / password endpoints ────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = %s", (body.email,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        row = conn.execute(
            "INSERT INTO users(email, name, password_hash, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (body.email, body.name, hash_password(body.password), body.role),
        ).fetchone()
        uid = row["id"]

    token = create_access_token({"sub": str(uid), "role": body.role})
    return TokenResponse(access_token=token, role=body.role, name=body.name, user_id=uid)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, role, password_hash FROM users WHERE email = %s",
            (body.email,),
        ).fetchone()

    if row is None or not verify_password(body.password, row["password_hash"] or ""):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": str(row["id"]), "role": row["role"]})
    return TokenResponse(
        access_token=token, role=row["role"], name=row["name"], user_id=row["id"]
    )


@router.get("/me")
def me_endpoint(
    # inline dep to avoid circular import; deps module uses get_conn which is already imported
    creds: str | None = None,
):
    """Thin health-check / token test — use /auth/me with Bearer token."""
    return {"status": "use Authorization: Bearer <token> to reach protected routes"}


# ── Google OAuth ──────────────────────────────────────────────────────────────

GOOGLE_AUTH_URL    = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL   = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_SCOPES = "openid email profile"


@router.get("/google")
def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    url = (
        f"{GOOGLE_AUTH_URL}"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={_SCOPES.replace(' ', '%20')}"
        f"&access_type=offline"
    )
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(code: str):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data.get("error_description", "OAuth error"))

        info_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        info = info_resp.json()

    email = info["email"]
    name  = info.get("name", email.split("@")[0])
    sub   = info["sub"]

    with get_conn() as conn:
        row = conn.execute("SELECT id, name, role FROM users WHERE email = %s", (email,)).fetchone()
        if row is None:
            new_row = conn.execute(
                "INSERT INTO users(email, name, role, oauth_sub) VALUES (%s, %s, 'patient', %s) "
                "RETURNING id",
                (email, name, sub),
            ).fetchone()
            uid, role = new_row["id"], "patient"
        else:
            conn.execute("UPDATE users SET oauth_sub = %s WHERE id = %s", (sub, row["id"]))
            uid, role, name = row["id"], row["role"], row["name"]

    token = create_access_token({"sub": str(uid), "role": role})

    # Redirect back to the frontend with the token in the URL so the
    # browser can store it and navigate to the dashboard.
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(f"{frontend_url}/auth/callback?token={token}&role={role}&name={name}")
