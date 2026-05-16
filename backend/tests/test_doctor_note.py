"""Tests for POST /patients/{id}/doctor-note (admin-only Nemotron parse)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch


def _mock_risk_profile():
    return {
        "suggested_exercises": ["squat", "plank"],
        "risky_exercises":     ["deadlift"],
        "affected_body_parts": [{"part": "knee", "weight": 3.0}],
    }


def test_doctor_note_happy_path(test_app, admin_headers):
    with patch(
        "app.routers.patients._call_nemotron_for_note",
        new=AsyncMock(return_value=_mock_risk_profile()),
    ):
        r = test_app.post(
            "/patients/P001/doctor-note",
            json={"note": "Post-ACL repair week 8. Avoid heavy load on the knee."},
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["patient_id"] == "P001"
    assert body["risk_profile"]["suggested_exercises"] == ["squat", "plank"]
    assert body["risk_profile"]["risky_exercises"]     == ["deadlift"]
    assert body["risk_profile"]["affected_body_parts"] == [{"part": "knee", "weight": 3.0}]


def test_doctor_note_persists(test_app, admin_headers):
    with patch(
        "app.routers.patients._call_nemotron_for_note",
        new=AsyncMock(return_value=_mock_risk_profile()),
    ):
        test_app.post(
            "/patients/P002/doctor-note",
            json={"note": "Rotator cuff repair, week 12."},
            headers=admin_headers,
        )

    profile = test_app.get("/patients/P002", headers=admin_headers).json()
    assert profile["doctor_note"] == "Rotator cuff repair, week 12."
    assert profile["risk_profile"]["risky_exercises"] == ["deadlift"]


def test_doctor_note_seeds_counts_with_zero(test_app, admin_headers):
    """Suggested exercises that are NOT yet in the patient's count table
    should be inserted with session_count=0 (so future real sessions outrank them).
    Existing counts must NOT be overwritten."""
    with patch(
        "app.routers.patients._call_nemotron_for_note",
        new=AsyncMock(return_value={
            "suggested_exercises": ["bench press", "pull up"],
            "risky_exercises": [],
            "affected_body_parts": [],
        }),
    ):
        test_app.post(
            "/patients/P001/doctor-note",
            json={"note": "Test."},
            headers=admin_headers,
        )

    # P001 already has squat=10 from seed; bench press / pull up are new.
    from app.db.database import get_conn
    with get_conn() as conn:
        rows = {r["exercise_name"]: r["session_count"]
                for r in conn.execute(
                    "SELECT exercise_name, session_count FROM patient_exercise_counts "
                    "WHERE patient_id = 'P001'"
                ).fetchall()}
    assert rows.get("bench press") == 0
    assert rows.get("pull up") == 0
    # Existing seed must not be clobbered
    assert rows.get("squat") == 10


def test_doctor_note_unknown_patient(test_app, admin_headers):
    r = test_app.post(
        "/patients/PZZZZZZ/doctor-note",
        json={"note": "Anything."},
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_doctor_note_requires_admin(test_app, patient_headers):
    r = test_app.post(
        "/patients/P001/doctor-note",
        json={"note": "Anything."},
        headers=patient_headers,
    )
    assert r.status_code == 403


def test_doctor_note_empty_rejected(test_app, admin_headers):
    r = test_app.post(
        "/patients/P001/doctor-note",
        json={"note": ""},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_doctor_note_too_long_rejected(test_app, admin_headers):
    r = test_app.post(
        "/patients/P001/doctor-note",
        json={"note": "x" * 20001},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_invalid_exercises_filtered_out(test_app, admin_headers):
    """Names not in KAGGLE_EXERCISES must be silently dropped."""
    with patch(
        "app.routers.patients._call_nemotron_for_note",
        new=AsyncMock(return_value={
            "suggested_exercises": ["squat", "imaginary lift", "moonwalk"],
            "risky_exercises":     ["deadlift", "fake exercise"],
            "affected_body_parts": [],
        }),
    ):
        # Use the sanitizer indirectly by passing through Nemotron mock.
        # The endpoint receives whatever the mock returns, so to actually
        # exercise the sanitizer we need the real path — call _sanitize_risk_profile.
        from app.routers.patients import _sanitize_risk_profile
        cleaned = _sanitize_risk_profile({
            "suggested_exercises": ["squat", "imaginary lift", "moonwalk"],
            "risky_exercises":     ["deadlift", "fake exercise"],
            "affected_body_parts": [],
        })
    assert cleaned["suggested_exercises"] == ["squat"]
    assert cleaned["risky_exercises"] == ["deadlift"]


def test_body_parts_malformed_dropped():
    from app.routers.patients import _sanitize_risk_profile
    cleaned = _sanitize_risk_profile({
        "suggested_exercises": [],
        "risky_exercises": [],
        "affected_body_parts": [
            {"part": "knee", "weight": 2.0},
            {"part": "", "weight": 1.0},                # blank part
            {"part": "elbow"},                          # missing weight
            {"weight": 3.0},                            # missing part
            {"part": "shoulder", "weight": "not numeric"},  # bad weight
            "totally wrong shape",
        ],
    })
    assert cleaned["affected_body_parts"] == [{"part": "knee", "weight": 2.0}]


def test_body_parts_weight_clamped():
    from app.routers.patients import _sanitize_risk_profile
    cleaned = _sanitize_risk_profile({
        "suggested_exercises": [],
        "risky_exercises": [],
        "affected_body_parts": [
            {"part": "knee",      "weight": 50.0},   # over 10
            {"part": "elbow",     "weight": 0.0},    # under 0.1
            {"part": "shoulder",  "weight": 5.5},    # ok
        ],
    })
    assert cleaned["affected_body_parts"] == [
        {"part": "knee", "weight": 10.0},
        {"part": "elbow", "weight": 0.1},
        {"part": "shoulder", "weight": 5.5},
    ]


def test_nemotron_returns_non_dict_falls_back():
    from app.routers.patients import _sanitize_risk_profile
    cleaned = _sanitize_risk_profile(["not", "a", "dict"])
    assert cleaned == {
        "suggested_exercises": [],
        "risky_exercises": [],
        "affected_body_parts": [],
    }
