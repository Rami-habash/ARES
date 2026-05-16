from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[3]   # repo root

# Single combined DB — clinical + app data in one place
DB_PATH = ROOT_DIR / "claw" / "data" / "patients.db"

# ── Auth ──────────────────────────────────────────────────────────────────────
SECRET_KEY       = os.environ.get("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_please")
ALGORITHM        = "HS256"
ACCESS_TOKEN_TTL = int(os.environ.get("ACCESS_TOKEN_TTL", 60 * 24))  # minutes

# Google OAuth — set these in .env for real OAuth flow
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

# ── CV API ────────────────────────────────────────────────────────────────────
# CV_API_BASE is the URL the backend uses for HTTP calls (check_in, checkout,
# marker.png). When CV is fronted by ngrok / Cloudflare so phones can reach it,
# set this to the public URL so /gym/check_in returns a marker URL the phone
# can open directly.
CV_API_BASE = os.environ.get("CV_API_BASE", "http://localhost:8001")

# CV_INTERNAL_BASE is what the backend uses for its long-lived WebSocket
# subscriber to /live/events. Defaults to localhost since the backend and CV
# usually share a host — no point routing through ngrok for an internal call.
CV_INTERNAL_BASE = os.environ.get("CV_INTERNAL_BASE", "http://localhost:8001")

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
