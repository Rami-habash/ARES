"""Sanity smoke test for the test fixtures."""

def test_health(test_app):
    r = test_app.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_admin_login_works(admin_headers, test_app):
    r = test_app.get("/patients", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "patients" in data
    assert len(data["patients"]) >= 4
