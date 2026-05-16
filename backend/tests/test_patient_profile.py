"""Tests for the patient profile response shape."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch


def test_seeded_patient_has_required_keys(test_app, admin_headers):
    r = test_app.get("/patients/P001", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("id", "name", "doctor_note", "risk_profile", "assigned_exercises"):
        assert key in body, f"missing key: {key}"


def test_seeded_patient_blank_doctor_note(test_app, admin_headers):
    r = test_app.get("/patients/P001", headers=admin_headers).json()
    assert r["doctor_note"] is None
    assert r["risk_profile"] == {}


def test_seeded_patient_top3_common_exercises(test_app, admin_headers):
    """P001 was seeded with squat=10, hip thrust=9, leg extension=8, plank=7.
    Top-3 should be squat, hip thrust, leg extension (plank excluded)."""
    r = test_app.get("/patients/P001", headers=admin_headers).json()
    exs = set(r["assigned_exercises"])
    assert exs == {"squat", "hip thrust", "leg extension"}
    assert "plank" not in exs


def test_risk_profile_returns_dict_not_string(test_app, admin_headers):
    """After a doctor-note upload, the GET response must carry the dict, not
    the raw JSON string we stored in risk_profile_json."""
    with patch(
        "app.routers.patients._call_nemotron_for_note",
        new=AsyncMock(return_value={
            "suggested_exercises": ["plank"],
            "risky_exercises": [],
            "affected_body_parts": [{"part": "back", "weight": 1.5}],
        }),
    ):
        test_app.post(
            "/patients/P003/doctor-note",
            json={"note": "Chronic LBP."},
            headers=admin_headers,
        )
    body = test_app.get("/patients/P003", headers=admin_headers).json()
    assert isinstance(body["risk_profile"], dict)
    assert body["risk_profile"]["affected_body_parts"] == [{"part": "back", "weight": 1.5}]


def test_blank_patient_endpoints(test_app, admin_headers):
    """A freshly-created patient (no doctor note, no sessions) must have
    risk_profile == {} and doctor_note == None."""
    created = test_app.post(
        "/patients",
        json={"name": "Blank Slate", "date_of_birth": "2000-01-01"},
        headers=admin_headers,
    ).json()
    pid = created["id"]

    g = test_app.get(f"/patients/{pid}", headers=admin_headers).json()
    assert g["doctor_note"] is None
    assert g["risk_profile"] == {}
    assert g["assigned_exercises"] == []
