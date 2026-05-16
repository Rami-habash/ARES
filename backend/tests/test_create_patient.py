"""Tests for POST /patients (admin-only blank patient creation)."""
from __future__ import annotations

import re


def test_create_patient_admin_succeeds(test_app, admin_headers):
    r = test_app.post(
        "/patients",
        json={"name": "New Patient", "date_of_birth": "1990-05-15"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert re.match(r"^P[0-9A-F]{6}$", body["id"]), body["id"]
    assert body["name"] == "New Patient"
    assert body["date_of_birth"] == "1990-05-15"
    assert body["assigned_exercises"] == []
    assert body["risk_profile"] == {}
    assert body["doctor_note"] is None
    assert body["linked_user_id"] is None


def test_created_patient_is_retrievable(test_app, admin_headers):
    r = test_app.post(
        "/patients",
        json={"name": "Retrieve Me", "date_of_birth": "1980-01-01"},
        headers=admin_headers,
    )
    new_id = r.json()["id"]

    g = test_app.get(f"/patients/{new_id}", headers=admin_headers)
    assert g.status_code == 200
    profile = g.json()
    assert profile["name"] == "Retrieve Me"
    assert profile["assigned_exercises"] == []
    assert profile["risk_profile"] == {}


def test_create_patient_requires_admin(test_app, patient_headers):
    r = test_app.post(
        "/patients",
        json={"name": "X", "date_of_birth": "1990-01-01"},
        headers=patient_headers,
    )
    assert r.status_code == 403


def test_create_patient_invalid_date(test_app, admin_headers):
    r = test_app.post(
        "/patients",
        json={"name": "Bad Date", "date_of_birth": "1990/01/01"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_create_patient_empty_name(test_app, admin_headers):
    r = test_app.post(
        "/patients",
        json={"name": "", "date_of_birth": "1990-01-01"},
        headers=admin_headers,
    )
    assert r.status_code == 422
