"""Verify that exercise counts update top-3 and that POST /sessions does NOT
double-count (single source of truth is the daemon PATIENT_PAUSED path)."""
from __future__ import annotations


def test_increment_count_updates_top3(test_app, admin_headers):
    """Calling increment_exercise_count directly (simulates the daemon) must
    flow through to /patients/{id}.assigned_exercises."""
    from patient_profile.profile import increment_exercise_count

    # P004 seeded: squat=8, push-up=7, lat pulldown=6, leg raises=5, plank=3
    # Pump push-up up to 15 — now top: push-up(15), squat(8), lat pulldown(6)
    for _ in range(8):
        increment_exercise_count("P004", "push-up")

    body = test_app.get("/patients/P004", headers=admin_headers).json()
    exs = set(body["assigned_exercises"])
    assert "push-up" in exs
    assert "squat" in exs
    assert "lat pulldown" in exs
    # plank had count=3, should still be excluded
    assert "plank" not in exs


def test_new_exercise_promotes_to_top3(test_app, admin_headers):
    """An exercise not seen before, once hit enough, makes the top-3."""
    from patient_profile.profile import increment_exercise_count

    # P003 seeded: plank=12, russian twist=10, romanian deadlift=6, hip thrust=4
    # Pump deadlift to 15 — it should overtake romanian deadlift
    for _ in range(15):
        increment_exercise_count("P003", "deadlift")

    exs = set(test_app.get("/patients/P003", headers=admin_headers).json()["assigned_exercises"])
    assert exs == {"deadlift", "plank", "russian twist"}


def test_post_sessions_does_not_double_count(test_app, admin_headers):
    """POST /sessions is post-hoc summary; it must NOT increment counts.
    The single source of truth is the form_monitor_daemon PATIENT_PAUSED path."""
    from app.db.database import get_conn

    with get_conn() as conn:
        before = {r["exercise_name"]: r["session_count"]
                  for r in conn.execute(
                      "SELECT exercise_name, session_count FROM patient_exercise_counts "
                      "WHERE patient_id = 'P001'"
                  ).fetchall()}

    test_app.post(
        "/sessions",
        json={
            "patient_id": "P001",
            "session_date": "2024-06-01",
            "exercises": ["squat", "plank"],
            "form_score": 80.0,
            "summary": "Good.",
        },
        headers=admin_headers,
    )

    with get_conn() as conn:
        after = {r["exercise_name"]: r["session_count"]
                 for r in conn.execute(
                     "SELECT exercise_name, session_count FROM patient_exercise_counts "
                     "WHERE patient_id = 'P001'"
                 ).fetchall()}

    assert before == after, "POST /sessions must not change exercise counts"
