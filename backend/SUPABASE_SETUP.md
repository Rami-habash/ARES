# Supabase Setup

ARES uses **Supabase Postgres** as the single source of truth for both app
data (users, alerts, sessions, gym lifecycle) and clinical data (patients,
exercises, session memories). This replaces the previous local SQLite file at
`claw/data/patients.db`.

## 1. Create a Supabase project

1. Sign in at <https://supabase.com> and click **New project**.
2. Pick a region close to wherever the backend will run.
3. Choose a strong database password — save it; you'll paste it into the
   connection string below.
4. Wait for provisioning to finish (~1 minute).

> Recommendation: create **two** projects — one for the demo (`ares`) and one
> for tests (`ares-test`). The test suite drops and re-creates tables on
> every run, so it must never point at a database with real data.

## 2. Grab the connection string

In your project: **Project Settings → Database → Connection string** tab →
**Session pooler** mode.

It looks like:

```
postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

> **Use the session pooler (port 5432), NOT the transaction pooler (port 6543).**
> psycopg's server-side prepared statements only work in session mode.

## 3. Configure backend/.env

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and fill in:

```dotenv
ARES_DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
ARES_TEST_DB_URL=postgresql://postgres.<test-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(48))">
```

## 4. Install dependencies and seed

```bash
cd backend
pip install -r requirements.txt
python -m app.db.seed             # creates tables + demo data
# or to wipe and re-seed:
python -m app.db.seed --reset
```

Open Supabase Studio → **Table editor** and you should see 10 tables with
demo rows (4 patients, 5 users, 5 alerts, 4 session_logs, 22 exercises).

## 5. Run the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The first request will lazily open a `psycopg_pool.ConnectionPool` against
Supabase. The pool stays open for the lifetime of the process.

## 6. Run tests

Tests require `ARES_TEST_DB_URL` to be set and pointing at a database whose
contents you don't mind losing.

```bash
cd backend
pytest -x
```

The suite:

- Drops every ARES table at session start
- Re-runs `init_db()` and `seed()`
- Wraps each individual test in a `force_rollback` transaction so writes
  vanish at teardown

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `RuntimeError: ARES_DB_URL is not set` at import time | `.env` not loaded — make sure you `cd backend` before running. |
| `psycopg.errors.InvalidPassword` | Bad password in the connection string. Re-copy from Supabase Studio. |
| `psycopg.errors.UndefinedTable: relation "users" does not exist` | Schema never created. Run `python -m app.db.seed`. |
| Connections hang for ~10s then fail | You used the **transaction** pooler (port 6543). Switch to **session** pooler (port 5432). |
| Tests fail with `pytest.skip: ARES_TEST_DB_URL is not set` | Add a separate test project to `.env`. |
