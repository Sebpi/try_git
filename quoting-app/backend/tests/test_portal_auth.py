"""Tests for the require_admin dependency's two credential paths: the local
X-Admin-Token (unchanged behavior) and a seb-portal JWT (new).

Uses FastAPI's TestClient against the real `main.app`, since the auth logic
lives at the dependency/middleware boundary, not something the agent-level
tests already cover.
"""
import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(monkeypatch, fresh_db):
    monkeypatch.setattr(main, "PORTAL_JWT_SECRET", "test-portal-secret")
    monkeypatch.setattr(main, "PORTAL_ADMIN_USERS", {"allowlisted-user"})
    with TestClient(main.app) as c:
        yield c


def _portal_jwt(**claims) -> str:
    base = {"iss": "seb-portal", "sub": "jordan", "iat": int(time.time())}
    base.update(claims)
    return pyjwt.encode(base, "test-portal-secret", algorithm="HS256")


def test_no_credentials_rejected(client):
    resp = client.get("/v1/threads")
    assert resp.status_code == 401


def test_local_admin_token_accepted(client):
    resp = client.get("/v1/threads", headers={"X-Admin-Token": main.ADMIN_TOKEN})
    assert resp.status_code == 200


def test_wrong_local_token_rejected(client):
    resp = client.get("/v1/threads", headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 401


def test_portal_jwt_with_admin_role_accepted(client):
    token = _portal_jwt(role="admin")
    resp = client.get("/v1/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"identity": "portal:jordan", "source": "portal"}


def test_portal_jwt_via_allowlist_accepted(client):
    token = _portal_jwt(sub="allowlisted-user", role="user")
    resp = client.get("/v1/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["identity"] == "portal:allowlisted-user"


def test_portal_jwt_without_admin_rejected(client):
    token = _portal_jwt(role="user")
    resp = client.get("/v1/threads", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_portal_jwt_wrong_issuer_rejected(client):
    token = _portal_jwt(iss="someone-else", role="admin")
    resp = client.get("/v1/threads", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_portal_jwt_bad_signature_rejected(client):
    token = pyjwt.encode({"iss": "seb-portal", "sub": "jordan", "role": "admin"}, "totally-wrong-secret", algorithm="HS256")
    resp = client.get("/v1/threads", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_portal_jwt_ignored_when_secret_unset(client, monkeypatch):
    monkeypatch.setattr(main, "PORTAL_JWT_SECRET", None)
    token = _portal_jwt(role="admin")
    resp = client.get("/v1/threads", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_dashboard_index_injects_signout_url(client, monkeypatch):
    monkeypatch.setattr(main, "PORTAL_SIGNOUT_URL", "https://portal.example/logout")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "https://portal.example/logout" in resp.text
    assert "%%PORTAL_SIGNOUT_URL%%" not in resp.text
