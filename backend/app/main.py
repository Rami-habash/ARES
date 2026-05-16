"""ARES Backend — FastAPI application entry point.

Run:
  cd backend && uvicorn app.main:app --reload --port 8000

First-time setup:
  cd backend && python -m app.db.seed          # create tables + demo users
  cd backend && python -m app.db.seed --reset  # wipe + re-seed

Demo credentials:
  admin@solstice.health / admin1234   (role=admin)
  alice@clinic.com      / patient1234 (role=patient, linked to P001)
  marcus@clinic.com     / patient1234 (role=patient, linked to P002)
  priya@clinic.com      / patient1234 (role=patient, linked to P003)
  diego@clinic.com      / patient1234 (role=patient, linked to P004)

Environment variables (.env):
  SECRET_KEY             — JWT signing secret (required in production)
  ACCESS_TOKEN_TTL       — token lifetime in minutes (default: 1440 = 24h)
  GOOGLE_CLIENT_ID       — for Google OAuth
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI
  NVIDIA_API_KEY         — for live Nemotron AI chat (optional; mocked otherwise)
  CV_API_BASE            — URL of the CV FastAPI service (default: http://localhost:8001)
  ALLOWED_ORIGINS        — comma-separated CORS origins
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS, DB_PATH
from app.db.database import init_db
from app.db.seed import seed
from patient_profile.profile import init_db as init_claw_db
from app.routers import ai, alerts, auth, gym, patients, sessions, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure schema exists; seed only if users table is empty.
    init_claw_db(DB_PATH)
    init_db()
    from app.db.database import get_conn
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        seed()

    # Re-attach form-monitor daemons for any session that was ACTIVE before we
    # restarted. Without this, an admin who restarts the backend mid-session
    # loses the coaching pipeline until the patient leaves+returns and CV
    # fires another patient_found event.
    from app.db.database import get_conn as _get_conn
    with _get_conn() as _c:
        _active = _c.execute(
            "SELECT patient_id FROM gym_sessions WHERE state = 'ACTIVE'"
        ).fetchall()
    for _row in _active:
        gym._start_daemon(_row["patient_id"])

    # Background task: mirror CV's identity lifecycle events into gym_sessions.
    stop = asyncio.Event()
    task = asyncio.create_task(gym.cv_event_subscriber(stop))
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="ARES — AI Rehab Room Backend",
    version="0.1.0",
    description=(
        "FastAPI backend for the Solstice ARES platform. "
        "Provides auth (email/password + Google OAuth), patient management, "
        "alerts, session logs, and AI assistant streaming."
    ),
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(patients.router)
app.include_router(alerts.router)
app.include_router(sessions.router)
app.include_router(gym.router)
app.include_router(ai.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ARES backend"}
