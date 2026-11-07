from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import config
from app.db import get_db
from app.garmin import sync as gsync
from app.garmin.client import GarminNotLoggedIn
from app.main import app

ACTIVITY = {"activityId": 99, "activityName": "Morning Run", "activityType": {"typeKey": "running"},
            "startTimeGMT": "2026-11-05 12:00:00", "distance": 5000.0, "duration": 1800.0,
            "averageHR": 150.0, "maxHR": 175.0, "averageSpeed": 2.78, "vO2MaxValue": 45.0}


class FakeGarmin:
    def get_activities_by_date(self, start, end):
        return [ACTIVITY]

    def get_stats(self, day):
        return {"totalSteps": 8000, "restingHeartRate": 55, "bodyBatteryHighestValue": 90,
                "bodyBatteryLowestValue": 20, "averageStressLevel": 30}

    def get_max_metrics(self, day):
        return [{"generic": {"vo2MaxPreciseValue": 45.3}}]


def _count(table):
    with get_db() as conn:
        return conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]


def test_sync_is_idempotent(monkeypatch):
    monkeypatch.setattr(gsync, "get_client", lambda: FakeGarmin())
    monkeypatch.setattr(gsync, "DAILY_DAYS", 2)
    first = gsync.sync_garmin()
    assert first["activities"] == 1 and first["daily"] >= 2
    daily = _count("garmin_daily")
    gsync.sync_garmin()
    assert _count("garmin_activity") == 1
    assert _count("garmin_daily") >= daily
    with get_db() as conn:
        row = conn.execute("SELECT * FROM garmin_activity").fetchone()
        assert row["sport"] == "running" and row["avg_hr"] == 150.0
        d = conn.execute("SELECT * FROM garmin_daily WHERE date = ?", (date.today().isoformat(),)).fetchone()
        assert d["vo2max"] == 45.3 and d["steps"] == 8000


def test_route_requires_login(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GARMIN_TOKENS", tmp_path / "missing")
    r = TestClient(app).post("/api/sync/garmin")
    assert r.status_code == 409


def test_get_client_without_tokens(monkeypatch, tmp_path):
    from app.garmin.client import get_client
    monkeypatch.setattr(config, "GARMIN_TOKENS", tmp_path / "missing")
    with pytest.raises(GarminNotLoggedIn):
        get_client()
