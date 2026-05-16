"""Live gym-presence endpoints — patient check-in / lost / leave lifecycle.

This is the live ArUco-marker-driven presence flow, separate from session_logs
(which records post-hoc exercise summaries). Lifecycle states stored in
``gym_sessions.state``:

  CHECKING_IN  → marker not yet seen by the camera
  ACTIVE       → marker seen, identity bound to a track_id
  LOST         → tracker lost the patient for >LOST_TIMEOUT_S (CV-side)
  LEFT         → patient left the gym (explicit checkout or "leave" tap)

The backend mirrors what CV reports; CV is the source of truth for ACTIVE/LOST
transitions, the backend owns CHECKING_IN/LEFT. The CV event subscriber runs
as a background task started in main.py's lifespan.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import websockets
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import CV_API_BASE, CV_INTERNAL_BASE
from app.db.database import get_conn

# TODO: these routes are currently unauthenticated so the patient web flow
# (and a future mobile app) can hit them without an admin JWT. Add a
# patient-token auth scheme before exposing this publicly.

log = logging.getLogger("ares.gym")

router = APIRouter(prefix="/gym", tags=["gym"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckInRequest(BaseModel):
    patient_id: str


class GymSessionResponse(BaseModel):
    id:          int
    patient_id:  str
    state:       str
    started_at:  str
    ended_at:    str | None = None
    last_event:  str | None = None
    marker_url:  str | None = None  # populated when the patient should be showing the marker


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_response(row, include_marker: bool) -> GymSessionResponse:
    return GymSessionResponse(
        id=row["id"],
        patient_id=row["patient_id"],
        state=row["state"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        last_event=row["last_event"],
        marker_url=f"{CV_API_BASE}/live/marker.png" if include_marker else None,
    )


def _active_session_for(patient_id: str) -> dict | None:
    """Return the most recent non-LEFT gym session for a patient, if any."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM gym_sessions WHERE patient_id = ? AND state != 'LEFT' "
            "ORDER BY started_at DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
    return dict(row) if row else None


def _set_state(session_id: int, state: str, last_event: str | None, ended: bool = False) -> None:
    with get_conn() as conn:
        if ended:
            conn.execute(
                "UPDATE gym_sessions SET state = ?, last_event = ?, "
                "ended_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                (state, last_event, session_id),
            )
        else:
            conn.execute(
                "UPDATE gym_sessions SET state = ?, last_event = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (state, last_event, session_id),
            )


async def _cv_post(path: str, json_body: dict) -> None:
    """Fire-and-mostly-forget POST to CV. Uses the internal URL so we don't
    bounce through ngrok for backend→CV calls. Logs errors but doesn't raise
    — the backend can stay healthy even if CV is temporarily down."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{CV_INTERNAL_BASE}{path}", json=json_body)
            r.raise_for_status()
    except Exception as exc:
        log.warning("CV %s failed: %s", path, exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/check_in", response_model=GymSessionResponse, status_code=201)
async def check_in(body: CheckInRequest):
    """
    Patient taps "Check in". Idempotent: if a session for this patient is
    already running, we re-arm CV's marker watch (in case CV was restarted
    and its in-memory registry got wiped) and return the existing session
    instead of forcing the patient to /leave first.
    """
    existing = _active_session_for(body.patient_id)
    if existing is not None:
        await _cv_post("/live/check_in", {"patient_id": body.patient_id})
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM gym_sessions WHERE id = ?", (existing["id"],)).fetchone()
        return _row_to_response(row, include_marker=row["state"] in ("CHECKING_IN", "LOST"))

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO gym_sessions(patient_id, state, last_event) VALUES (?, 'CHECKING_IN', 'check_in')",
            (body.patient_id,),
        )
        row = conn.execute("SELECT * FROM gym_sessions WHERE id = ?", (cur.lastrowid,)).fetchone()

    await _cv_post("/live/check_in", {"patient_id": body.patient_id})
    return _row_to_response(row, include_marker=True)


@router.post("/{session_id}/still_here", response_model=GymSessionResponse)
async def still_here(session_id: int):
    """Patient tapped "I'm still here" after a lost prompt. Flip back to
    CHECKING_IN, re-arm CV's marker watch, and return the marker URL."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM gym_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Gym session not found.")
    if row["state"] == "LEFT":
        raise HTTPException(status_code=409, detail="Gym session already ended.")

    _set_state(session_id, "CHECKING_IN", "still_here")
    await _cv_post("/live/check_in", {"patient_id": row["patient_id"]})

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM gym_sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_response(row, include_marker=True)


@router.post("/{session_id}/leave", response_model=GymSessionResponse)
async def leave(session_id: int):
    """Patient is leaving. Mark LEFT, tell CV to drop the binding."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM gym_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Gym session not found.")
    if row["state"] == "LEFT":
        return _row_to_response(row, include_marker=False)

    _set_state(session_id, "LEFT", "leave", ended=True)
    await _cv_post("/live/checkout", {"patient_id": row["patient_id"]})

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM gym_sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_response(row, include_marker=False)


@router.get("/{session_id}", response_model=GymSessionResponse)
def get_session(session_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM gym_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Gym session not found.")
    show_marker = row["state"] in ("CHECKING_IN", "LOST")
    return _row_to_response(row, include_marker=show_marker)


@router.get("", response_model=list[GymSessionResponse])
def list_active():
    """Every non-LEFT gym session in the room right now."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM gym_sessions WHERE state != 'LEFT' ORDER BY started_at DESC"
        ).fetchall()
    return [_row_to_response(r, include_marker=r["state"] in ("CHECKING_IN", "LOST")) for r in rows]


# ── CV event subscriber ───────────────────────────────────────────────────────

CV_EVENTS_URL = CV_INTERNAL_BASE.replace("http://", "ws://").replace("https://", "wss://") + "/live/events"


def _apply_cv_event(event: dict) -> None:
    """Translate a CV identity event into a gym_sessions state update."""
    patient_id = event.get("patient_id")
    event_type = event.get("type")
    if not patient_id or not event_type:
        return

    session = _active_session_for(patient_id)
    if session is None:
        log.info("CV event %s for %s has no active gym session — ignoring", event_type, patient_id)
        return

    if event_type == "patient_checked_in":
        _set_state(session["id"], "ACTIVE", event_type)
    elif event_type == "patient_lost":
        _set_state(session["id"], "LOST", event_type)
        # TODO: push notification to the patient phone. For now the dashboard
        # polling /gym/{id} will see state=LOST and surface the prompt.
    elif event_type == "patient_found":
        _set_state(session["id"], "ACTIVE", event_type)


async def cv_event_subscriber(stop_event: asyncio.Event) -> None:
    """
    Background task: subscribe to CV's /live/events WS, mirror events into
    gym_sessions state. Reconnects on disconnect with exponential backoff.
    """
    backoff = 1.0
    while not stop_event.is_set():
        try:
            log.info("Connecting to CV events at %s", CV_EVENTS_URL)
            async with websockets.connect(CV_EVENTS_URL) as ws:
                backoff = 1.0
                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning("CV sent non-JSON event: %r", raw[:200])
                        continue
                    if "error" in event:
                        # Shouldn't happen with the current CV impl (the WS waits
                        # for a session instead of erroring). Log and ignore so a
                        # surprise error message doesn't trigger fast reconnects.
                        log.warning("CV events error payload: %s", event["error"])
                        continue
                    _apply_cv_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("CV events disconnected (%s); retry in %.1fs", exc, backoff)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)
