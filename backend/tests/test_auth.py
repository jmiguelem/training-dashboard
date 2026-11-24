from fastapi.testclient import TestClient

from app import auth, config
from app.main import app

PROTECTED = ["/api/status", "/api/plan", "/api/profile", "/api/coach/chat", "/api/lifts", "/auth/whoop/login"]


def test_everything_requires_login():
    c = TestClient(app)
    for path in PROTECTED:
        assert c.get(path, follow_redirects=False).status_code == 401, path
    assert c.post("/api/sync/garmin").status_code == 401
    assert c.put("/api/profile", json={"goal": "x"}).status_code == 401
    assert c.get("/health").status_code == 200


def test_login_flow():
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert c.get("/api/auth/session").json() == {"authenticated": False}
    r = c.post("/api/auth/login", json={"password": "correct horse"})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/status").status_code == 200
    assert c.get("/api/auth/session").json() == {"authenticated": True}
    c.post("/api/auth/logout")
    assert c.get("/api/status").status_code == 401


def test_fails_closed_without_password(monkeypatch):
    monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "")
    c = TestClient(app)
    assert c.get("/api/status").status_code == 503
    assert c.post("/api/auth/login", json={"password": ""}).status_code == 503
    assert not auth.valid_token(auth.make_token())


def test_token_tamper_and_expiry():
    t = auth.make_token()
    assert auth.valid_token(t)
    exp, sig = t.split(".")
    assert not auth.valid_token(f"{int(exp) + 99999}.{sig}")
    assert not auth.valid_token("garbage")
    assert not auth.valid_token(t, now=int(exp) + 1)


def test_token_invalid_after_password_change(monkeypatch):
    t = auth.make_token()
    monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "different")
    assert not auth.valid_token(t)


def test_brute_force_lockout():
    c = TestClient(app)
    for _ in range(auth.MAX_FAILURES):
        assert c.post("/api/auth/login", json={"password": "bad"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": "correct horse"}).status_code == 429


def test_weak_password_warning(monkeypatch):
    assert auth.weak_password_warning() is None  # "correct horse" is 13 characters
    monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "short")
    assert "shorter than 12" in auth.weak_password_warning()
    monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "")
    assert "not set" in auth.weak_password_warning()
    monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "a-long-enough-password")
    assert auth.weak_password_warning() is None
