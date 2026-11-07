import time

import httpx
import respx
from fastapi.testclient import TestClient

from app import config
from app.db import get_db
from app.main import app
from app.whoop import auth
from app.whoop.sync import sync_whoop

BASE = config.WHOOP_API_BASE

CYCLE = {"id": 1, "start": "2026-11-01T08:00:00.000Z", "end": "2026-11-02T08:00:00.000Z",
         "score": {"strain": 10.5, "average_heart_rate": 70, "max_heart_rate": 160, "kilojoule": 9000}}
RECOVERY = {"cycle_id": 1, "sleep_id": "s1", "created_at": "2026-11-01T09:00:00.000Z",
            "score": {"recovery_score": 80, "resting_heart_rate": 50, "hrv_rmssd_milli": 70.5}}
SLEEP = {"id": "s1", "start": "2026-11-01T00:00:00.000Z", "end": "2026-11-01T08:00:00.000Z",
         "nap": False, "score": {"sleep_performance_percentage": 90,
                                 "stage_summary": {"total_rem_sleep_time_milli": 5000}}}
WORKOUT = {"id": "w1", "start": "2026-11-01T10:00:00.000Z", "end": "2026-11-01T11:00:00.000Z",
           "sport_name": "running", "score": {"strain": 8.0, "distance_meter": 5000}}


def _connect():
    auth._store_tokens({"access_token": "tok", "refresh_token": "ref", "expires_in": 3600})


def _mock_api(mock, cycle_pages=None):
    pages = cycle_pages or [{"records": [CYCLE], "next_token": None}]
    mock.get(f"{BASE}/cycle").mock(side_effect=[httpx.Response(200, json=p) for p in pages])
    mock.get(f"{BASE}/recovery").respond(json={"records": [RECOVERY]})
    mock.get(f"{BASE}/activity/sleep").respond(json={"records": [SLEEP]})
    mock.get(f"{BASE}/activity/workout").respond(json={"records": [WORKOUT]})


def _count(table):
    with get_db() as conn:
        return conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]


@respx.mock
def test_sync_is_idempotent():
    _connect()
    _mock_api(respx.mock)
    counts = sync_whoop()
    assert counts == {"cycles": 1, "recovery": 1, "sleep": 1, "workouts": 1}
    respx.reset()
    _mock_api(respx.mock)
    sync_whoop()
    for table in ("whoop_cycle", "whoop_recovery", "whoop_sleep", "whoop_workout"):
        assert _count(table) == 1


@respx.mock
def test_pagination_follows_next_token():
    _connect()
    c2 = {**CYCLE, "id": 2}
    _mock_api(respx.mock, [{"records": [CYCLE], "next_token": "abc"},
                           {"records": [c2], "next_token": None}])
    sync_whoop()
    assert _count("whoop_cycle") == 2
    second_call = respx.calls[1].request
    assert second_call.url.params["nextToken"] == "abc"


@respx.mock
def test_expired_token_is_refreshed():
    with get_db() as conn:
        conn.execute("INSERT INTO whoop_token VALUES (1, 'old', 'ref1', ?)", (time.time() - 10,))
    respx.post(config.WHOOP_TOKEN_URL).respond(
        json={"access_token": "new", "refresh_token": "ref2", "expires_in": 3600})
    assert auth.get_access_token() == "new"
    with get_db() as conn:
        assert conn.execute("SELECT refresh_token FROM whoop_token").fetchone()[0] == "ref2"


def test_callback_rejects_bad_state():
    client = TestClient(app)
    r = client.get("/auth/whoop/callback", params={"code": "x", "state": "nope"})
    assert r.status_code == 400


def test_sync_route_requires_connection():
    client = TestClient(app)
    assert client.post("/api/sync/whoop").status_code == 409
