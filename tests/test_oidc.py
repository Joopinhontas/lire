import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_auth import ENV


class FakeResponse:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=None)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for key, value in {**ENV, "OIDC_ISSUER": "https://id.example", "OIDC_CLIENT_ID": "lire",
                       "OIDC_CLIENT_SECRET": "s", "PUBLIC_URL": "https://lire.example"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    for name in ("main", "services"):
        sys.modules.pop(name, None)
    import main  # noqa: PLC0415
    main.bootstrap_admin()
    main._oidc_meta.update(authorization_endpoint="https://id.example/authorize",
                           token_endpoint="https://id.example/token", userinfo_endpoint="https://id.example/userinfo")

    async def fake_post(url, **kw):
        return FakeResponse({"access_token": "at"})

    async def fake_get(url, **kw):
        return FakeResponse({"preferred_username": "Lucas", "email": "lucas@example.org", "email_verified": True})

    monkeypatch.setattr(main.svc.http, "post", fake_post)
    monkeypatch.setattr(main.svc.http, "get", fake_get)
    return main, TestClient(main.app, base_url="https://lire.example", follow_redirects=False)


def test_session_announces_single_sign_on(client):
    _, c = client
    assert c.get("/api/session").json()["oidc"] == {"name": "SSO", "accounts": False}


def test_forged_state_is_refused(client):
    _, c = client
    start = c.get("/api/auth/oidc/start")
    assert start.status_code == 303 and "code_challenge_method=S256" in start.headers["location"]
    r = c.get("/api/auth/oidc/callback", params={"code": "x", "state": "not-the-one"})
    assert r.status_code == 303 and "login_error=sso_expired" in r.headers["location"]


def test_first_sign_in_creates_member_and_session(client):
    main, c = client
    start = c.get("/api/auth/oidc/start")
    state = dict(p.split("=", 1) for p in start.headers["location"].split("?", 1)[1].split("&"))["state"]
    r = c.get("/api/auth/oidc/callback", params={"code": "x", "state": state})
    assert r.status_code == 303 and r.headers["location"] == "/"
    with main.db() as con:
        assert con.execute("SELECT role FROM users WHERE username = 'lucas'").fetchone() == ("member",)
    assert c.get("/api/session").json()["user"] == {"username": "lucas", "role": "member"}


def test_kavita_key_of_someone_else_is_refused(client, monkeypatch):
    main, c = client
    start = c.get("/api/auth/oidc/start")
    state = dict(p.split("=", 1) for p in start.headers["location"].split("?", 1)[1].split("&"))["state"]
    c.get("/api/auth/oidc/callback", params={"code": "x", "state": state})

    async def other_owner(url, **kw):
        return FakeResponse({"username": "marc"})

    monkeypatch.setattr(main.svc.kavita.client, "post", other_owner)
    r = c.post("/api/me/kavita-key", json={"key": "k" * 32}, headers={"X-Lire": "1"})
    assert r.status_code == 403


def test_new_friend_gets_kavita_and_sign_in_accounts(client, monkeypatch):
    import asyncio
    main, _ = client
    made = {}

    async def fake_kavita_user(username, password):
        return "kavita-key"

    async def fake_ensure(username, email):
        made["email"] = email
        return {"id": "pid-1", "username": username}

    async def fake_link(user_id, ttl="168h"):
        return f"https://id.example/lc/{user_id}"

    monkeypatch.setattr(main.svc.kavita, "create_user", fake_kavita_user)
    monkeypatch.setattr(main.svc.pocket, "enabled", True)
    monkeypatch.setattr(main.svc.pocket, "ensure_user", fake_ensure)
    monkeypatch.setattr(main.svc.pocket, "login_link", fake_link)
    res = asyncio.run(main.create_user(main.NewUser(username="Lucas")))
    assert res["sso_link"] == "https://id.example/lc/pid-1" and res["sso_note"] is None
    assert made["email"] == "lucas@lire.invalid"
