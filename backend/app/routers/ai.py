"""AI assistant endpoints.

/ai/chat      — streaming chat response (SSE) backed by the NemoDemo exercise
                identifier reasoning chain.  Falls back to a structured mock
                when NVIDIA_API_KEY is not set.

/ai/chat/sync — non-streaming version for easy frontend testing.

Both endpoints support two contexts:
  - Admin: can ask about any patient (RAG over all session logs + alert history)
  - Patient: scoped to their own data only
"""
from __future__ import annotations

import json
import os
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.db.database import get_conn

router = APIRouter(prefix="/ai", tags=["ai"])

NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NEMOTRON_MODEL  = "nvidia/nemotron-3-nano-30b-a3b"


# ── Context builders ──────────────────────────────────────────────────────────

def _admin_context(query: str) -> str:
    rows = []
    with get_conn() as conn:
        patients = conn.execute("SELECT id, name, notes FROM patients ORDER BY id").fetchall()
        for p in patients:
            exercises = [
                r["name"] for r in conn.execute(
                    "SELECT e.name FROM exercises e JOIN patient_exercises pe ON pe.exercise_id=e.id "
                    "WHERE pe.patient_id=?", (p["id"],)
                )
            ]
            rows.append(f"Patient {p['id']} ({p['name']}): {p['notes']}. Common exercises: {', '.join(exercises)}")

        alerts = conn.execute(
            "SELECT patient_id, severity, title, description FROM alerts WHERE status='Open' LIMIT 20"
        ).fetchall()
        alert_lines = [f"[{a['severity']}] {a['patient_id']}: {a['title']} — {a['description']}" for a in alerts]

        sessions = conn.execute(
            "SELECT patient_id, session_date, form_score, summary FROM session_logs ORDER BY session_date DESC LIMIT 10"
        ).fetchall()
        session_lines = [f"{s['patient_id']} on {s['session_date']}: form={s['form_score']}, {s['summary']}" for s in sessions]

    return (
        "You are ARES, an AI clinical assistant for a physical therapy clinic.\n\n"
        "## Patient roster\n" + "\n".join(rows) + "\n\n"
        "## Open alerts\n" + "\n".join(alert_lines or ["None"]) + "\n\n"
        "## Recent sessions\n" + "\n".join(session_lines or ["None"])
    )


def _patient_context(user_id: int) -> tuple[str, str | None]:
    """Returns (system_prompt, patient_id | None)."""
    with get_conn() as conn:
        link = conn.execute(
            "SELECT nemo_patient_id FROM patient_links WHERE user_id = ?", (user_id,)
        ).fetchone()
        if link is None:
            return "You are ARES, a physical therapy assistant. The user has no linked patient profile.", None

        pid = link["nemo_patient_id"]
        row = conn.execute("SELECT id, name, notes FROM patients WHERE id=?", (pid,)).fetchone()
        exercises = [
            r["name"] for r in conn.execute(
                "SELECT e.name FROM exercises e JOIN patient_exercises pe ON pe.exercise_id=e.id "
                "WHERE pe.patient_id=?", (pid,)
            )
        ]
        memories = [
            r["highlight"] for r in conn.execute(
                "SELECT highlight FROM session_memories WHERE patient_id=? ORDER BY created_at DESC LIMIT 5",
                (pid,),
            )
        ]
        sessions = conn.execute(
            "SELECT session_date, form_score, summary FROM session_logs WHERE patient_id=? ORDER BY session_date DESC LIMIT 5",
            (pid,),
        ).fetchall()
        alerts = conn.execute(
            "SELECT severity, title, description FROM alerts WHERE patient_id=? AND status='Open'",
            (pid,),
        ).fetchall()

    patient_info = ""
    if row:
        patient_info = (
            f"Patient: {row['name']}\nNotes: {row['notes']}\n"
            f"Common exercises: {', '.join(exercises)}\n"
            "Recent session highlights:\n" + "\n".join(f"- {m}" for m in memories)
        )

    session_lines = [f"{s['session_date']}: form={s['form_score']}, {s['summary']}" for s in sessions]
    alert_lines = [f"[{a['severity']}] {a['title']}: {a['description']}" for a in alerts]

    system = (
        "You are ARES, a personal rehab coach assistant. Only discuss this patient's data.\n\n"
        + patient_info
        + "\n\n## Recent sessions\n" + "\n".join(session_lines or ["None"])
        + "\n\n## Active alerts\n" + "\n".join(alert_lines or ["None"])
    )
    return system, pid


# ── Mock streaming (no API key) ────────────────────────────────────────────────

MOCK_STEPS = [
    "Retrieving patient session data...",
    "Analyzing movement patterns across last 3 sessions...",
    "Cross-referencing clinical protocols...",
    "Generating coaching recommendation...",
]

MOCK_ANSWER = (
    "Based on the available session data, I can see patterns in your movement logs. "
    "Focus on maintaining consistent form throughout each rep. "
    "Your recent session scores suggest improvement in core stability — keep it up!"
)


async def _mock_stream(query: str) -> AsyncGenerator[str, None]:
    import asyncio
    for step in MOCK_STEPS:
        await asyncio.sleep(0.5)
        yield f"data: {json.dumps({'type': 'step', 'content': step})}\n\n"
    await asyncio.sleep(0.4)
    yield f"data: {json.dumps({'type': 'answer', 'content': MOCK_ANSWER})}\n\n"
    yield "data: [DONE]\n\n"


async def _nvidia_stream(system: str, query: str) -> AsyncGenerator[str, None]:
    import httpx, asyncio
    messages = [{"role": "system", "content": system}, {"role": "user", "content": query}]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream(
                "POST",
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                json={"model": NEMOTRON_MODEL, "messages": messages, "stream": True, "max_tokens": 512},
            ) as resp:
                buffer = ""
                async for chunk in resp.aiter_text():
                    for line in chunk.splitlines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            if buffer:
                                yield f"data: {json.dumps({'type': 'answer', 'content': buffer})}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            delta = json.loads(raw)["choices"][0]["delta"].get("content", "")
                            buffer += delta
                        except Exception:
                            pass
    except Exception as e:
        yield f"data: {json.dumps({'type': 'answer', 'content': f'Error: {e}'})}\n\n"
        yield "data: [DONE]\n\n"


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    patient_id: str | None = None   # admin can scope to a specific patient


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat_stream(body: ChatRequest, user: dict = Depends(get_current_user)):
    if user["role"] == "admin":
        system = _admin_context(body.query)
    else:
        system, _ = _patient_context(user["id"])

    if NVIDIA_API_KEY:
        gen = _nvidia_stream(system, body.query)
    else:
        gen = _mock_stream(body.query)

    return StreamingResponse(gen, media_type="text/event-stream")


@router.post("/chat/sync")
async def chat_sync(body: ChatRequest, user: dict = Depends(get_current_user)):
    """Non-streaming version: collects the full answer and returns JSON."""
    if user["role"] == "admin":
        system = _admin_context(body.query)
    else:
        system, _ = _patient_context(user["id"])

    if not NVIDIA_API_KEY:
        return {"answer": MOCK_ANSWER, "steps": MOCK_STEPS}

    import httpx
    messages = [{"role": "system", "content": system}, {"role": "user", "content": body.query}]
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
            json={"model": NEMOTRON_MODEL, "messages": messages, "max_tokens": 512},
        )
        data = resp.json()

    answer = data["choices"][0]["message"]["content"]
    return {"answer": answer}
