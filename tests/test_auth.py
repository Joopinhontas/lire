import sys
import time
from pathlib import Path

import pytest

ENV = {
    "PROWLARR_URL": "http://x", "PROWLARR_API_KEY": "k", "QBIT_URL": "http://x", "QBIT_USER": "u",
    "QBIT_PASSWORD": "p", "KAVITA_URL": "http://x", "KAVITA_API_KEY": "k", "LIRE_PASSWORD": "boot-pass",
    "SESSION_SECRET": "s" * 64,
}


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    for name in ("main", "services"):
        sys.modules.pop(name, None)
    import main  # noqa: PLC0415
    main.bootstrap_admin()
    return main


def test_password_hash_roundtrip(app_module):
    stored = app_module.hash_password("abcd-efgh")
    assert stored.startswith("scrypt$")
    assert app_module.check_password("abcd-efgh", stored)
    assert not app_module.check_password("abcd-efgX", stored)
    assert not app_module.check_password("x", "garbage")


def test_bootstrap_admin_logs_in_with_existing_password(app_module):
    with app_module.db() as con:
        row = con.execute("SELECT id, pw_hash, role FROM users WHERE username = 'admin'").fetchone()
    assert row[2] == "admin" and app_module.check_password("boot-pass", row[1])


def test_session_roundtrip_and_tampering(app_module):
    token = app_module.make_session(1, 1)
    assert app_module.session_user(token)["username"] == "admin"
    uid, ver, exp, sig = token.split(".")
    assert app_module.session_user(f"2.{ver}.{exp}.{sig}") is None
    assert app_module.session_user(f"{uid}.{ver}.{int(exp) + 1}.{sig}") is None
    expired = f"1.1.{int(time.time()) - 10}"
    assert app_module.session_user(f"{expired}.{app_module.sign(expired)}") is None
    assert app_module.session_user("1.2.3") is None
    assert app_module.session_user(None) is None


def test_session_dies_with_deleted_user(app_module):
    with app_module.db() as con:
        con.execute("INSERT INTO users (username, pw_hash, role, created_at) VALUES ('ami','x','member',0)")
        uid = con.execute("SELECT id FROM users WHERE username='ami'").fetchone()[0]
    token = app_module.make_session(uid, 1)
    assert app_module.session_user(token)["role"] == "member"
    with app_module.db() as con:
        con.execute("DELETE FROM users WHERE id = ?", (uid,))
    assert app_module.session_user(token) is None


def test_within_only_matches_real_subpaths(app_module):
    w = app_module._within
    assert w("/data/manga/Berserk", "/data/manga/Berserk")
    assert w("/data/manga/Berserk/T42/", "/data/manga/Berserk")
    assert not w("/data/manga/Berserk of Gluttony", "/data/manga/Berserk")
    assert not w("/data/manga", "/data/manga/Berserk")
    assert not w("", "/data/manga/Berserk")


def test_username_rule(app_module):
    ok = app_module.USERNAME_RE.match
    assert ok("lucas") and ok("j.doe-2")
    assert not ok("Lucas") and not ok("a") and not ok("../x") and not ok("x y")


def test_password_reset_revokes_existing_sessions(app_module):
    token = app_module.make_session(1, 1)
    assert app_module.session_user(token)
    with app_module.db() as con:
        con.execute("UPDATE users SET session_version = session_version + 1 WHERE id = 1")
    assert app_module.session_user(token) is None
    assert app_module.session_user(app_module.make_session(1, 2))["username"] == "admin"


def test_forwarded_ip_only_trusted_from_proxy(app_module):
    class Req:
        def __init__(self, peer, real):
            self.client = type("C", (), {"host": peer})()
            self.headers = {"x-real-ip": real}
    assert app_module.client_ip(Req("172.18.0.1", "90.1.2.3")) == "90.1.2.3"
    assert app_module.client_ip(Req("203.0.113.50", "1.1.1.1")) == "203.0.113.50"


def test_throttle_window(app_module):
    bucket = {}
    for _ in range(3):
        assert not app_module.throttled(bucket, "k", 3, 60)
        bucket["k"].append(time.time())
    assert app_module.throttled(bucket, "k", 3, 60)
