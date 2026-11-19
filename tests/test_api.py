import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(home, conn):
    from stackloom import accounts
    from stackloom.api.app import create_app

    accounts.bootstrap(conn)
    accounts.throttle.clear("admin")
    return TestClient(create_app(home, background=False), base_url="http://127.0.0.1:4999")


def login(client, password="1234567890@"):
    r = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def test_health_open_everything_else_needs_session(client):
    assert client.get("/api/health").json()["app"] == "stackloom"
    assert client.get("/api/projects").status_code == 401


def test_host_header_rejected(home, conn):
    from stackloom.api.app import create_app

    evil = TestClient(create_app(home, background=False), base_url="http://evil.example:4999")
    assert evil.get("/api/health").status_code == 421


def test_must_change_password_gate_and_csrf(client):
    csrf = login(client)
    assert client.get("/api/projects").status_code == 403
    r = client.post("/api/auth/password", json={"current": "1234567890@", "new": "a-long-new-password"})
    assert r.status_code == 403  # no CSRF header
    r = client.post("/api/auth/password", json={"current": "1234567890@", "new": "a-long-new-password"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert client.get("/api/projects").json() == []
    assert client.get("/api/overview").json()["projects"] == 0
    assert client.post("/api/discovery/scan").status_code == 403


def test_logout_ends_session(client):
    csrf = login(client)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert client.get("/api/auth/me").status_code == 401


def test_security_headers(client):
    r = client.get("/api/health")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
