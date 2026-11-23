import pytest

from app import config, db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "WHOOP_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "WHOOP_CLIENT_SECRET", "secret")
    db.init_db()


@pytest.fixture(autouse=True)
def login_bypass(request, monkeypatch):
    """Other tests exercise routes directly; test_auth.py tests the real gate."""
    from app import auth

    if request.module.__name__.endswith("test_auth"):
        monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "correct horse")
        auth._failures.clear()
    else:
        monkeypatch.setattr(config, "DASHBOARD_PASSWORD", "x")
        monkeypatch.setattr(auth, "is_authenticated", lambda request: True)
