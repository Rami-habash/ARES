# ARES Backend

FastAPI backend for the Solstice ARES physical therapy platform.

## Quick start

```bash
cd backend

# 1. Install deps
pip install -r requirements.txt

# 2. Seed the DB (clinical + auth data in one pass)
python -m app.db.seed

# 3. Start the server
python -m uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs

## Demo credentials

| Email | Password | Role |
|-------|----------|------|
| admin@solstice.health | admin1234 | admin |
| alice@clinic.com | patient1234 | patient (→ P001) |
| marcus@clinic.com | patient1234 | patient (→ P002) |
| priya@clinic.com | patient1234 | patient (→ P003) |
| diego@clinic.com | patient1234 | patient (→ P004) |

## Connecting the frontend

In `frontend/.env.local`:

```
NEXT_PUBLIC_USE_MOCK=false
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Environment variables

Copy `.env.example` → `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | JWT signing secret |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `NVIDIA_API_KEY` | Nemotron AI chat (optional) |
| `CV_API_BASE` | URL of the CV pipeline service |

## Architecture

```
backend/
├── app/
│   ├── main.py            # FastAPI app, CORS, lifespan
│   ├── core/
│   │   ├── config.py      # Env var configuration
│   │   ├── deps.py        # get_current_user, require_admin
│   │   └── security.py    # bcrypt + JWT
│   ├── db/
│   │   ├── database.py    # SQLite schema (users, alerts, sessions)
│   │   └── seed.py        # Demo data seeder
│   └── routers/
│       ├── auth.py        # POST /auth/login, /register, GET /auth/google
│       ├── users.py       # GET /users, PUT /users/:id/role, link-patient
│       ├── patients.py    # GET /patients, /patients/me, /patients/:id
│       ├── alerts.py      # GET/POST/PATCH/DELETE /alerts
│       ├── sessions.py    # GET/POST /sessions
│       └── ai.py          # POST /ai/chat (SSE), /ai/chat/sync
```

### Data model

Single SQLite DB at `NemoDemo/data/patients.db`:

| Table | Owner | Description |
|-------|-------|-------------|
| `patients` | clinical | Patient demographics and notes |
| `exercises` | clinical | Kaggle exercise catalog |
| `patient_exercises` | clinical | Prescribed exercise assignments |
| `session_memories` | clinical | Append-only session highlight log |
| `users` | app | Login accounts with roles |
| `patient_links` | app | Maps user account → patient record |
| `alerts` | app | Flagged movement events |
| `session_logs` | app | Per-session summaries and form scores |
