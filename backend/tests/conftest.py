import pytest

from app import config, db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "WHOOP_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "WHOOP_CLIENT_SECRET", "secret")
    db.init_db()
