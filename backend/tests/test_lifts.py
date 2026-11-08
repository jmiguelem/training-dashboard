import pytest
from fastapi.testclient import TestClient

from app import lifts
from app.db import get_db
from app.main import app


def gset(name, reps, weight_g, dur, kind="ACTIVE"):
    if kind == "REST":
        return {"setType": "REST", "duration": dur, "exercises": []}
    return {"setType": "ACTIVE", "exercises": [{"name": name, "category": "X"}], "repetitionCount": reps,
            "weight": weight_g, "duration": dur, "startTime": "2026-11-01T10:00:00.0"}


def add_activity(i=1, start="2026-11-01 10:00:00"):
    with get_db() as conn:
        conn.execute("INSERT INTO garmin_activity (id, sport, start, duration_s, raw) "
                     "VALUES (?, 'strength_training', ?, 3600, '{}')", (i, start))


SETS = [gset("BARBELL_BACK_SQUAT", 8, 70000, 45), gset(None, None, None, 120, "REST"),
        gset("BARBELL_BACK_SQUAT", 8, 80000, 40), gset(None, None, None, 90, "REST"),
        gset("BARBELL_BACK_SQUAT", 1, 80000, 1)]  # 1 s: start button missed


def test_import_converts_units_and_attaches_rest():
    add_activity()
    assert lifts.import_sets(1, SETS) == 3
    s = lifts.sessions(30)[0]
    assert [x["weight_kg"] for x in s["sets"]] == [70.0, 80.0, 80.0]
    assert s["sets"][0]["rest_s"] == 120


def test_short_sets_are_suspect_and_excluded_from_stats():
    add_activity()
    lifts.import_sets(1, SETS)
    s = lifts.sessions(30)[0]
    assert s["suspect_sets"] == 1
    assert s["volume_kg"] == 70 * 8 + 80 * 8
    h = lifts.exercise_history()[0]
    assert h["best_weight_kg"] == 80.0 and h["history"][0]["top_reps"] == 8
    assert h["best_e1rm"] == round(80 * (1 + 8 / 30), 1)


def test_edit_fixes_a_missed_set_and_survives_resync():
    add_activity()
    lifts.import_sets(1, SETS)
    bad = [x for x in lifts.sessions(30)[0]["sets"] if x["suspect"]][0]
    fixed = lifts.update_set(bad["id"], {"reps": 6, "duration_s": 40})
    assert fixed["edited"] == 1 and fixed["suspect"] is False
    lifts.import_sets(1, SETS)  # Garmin sync runs again with the original values
    again = [x for x in lifts.sessions(30)[0]["sets"] if x["id"] == bad["id"]][0]
    assert again["reps"] == 6
    assert lifts.sessions(30)[0]["suspect_sets"] == 0


def test_deleted_set_stays_deleted_after_resync():
    add_activity()
    lifts.import_sets(1, SETS)
    sid = lifts.sessions(30)[0]["sets"][0]["id"]
    lifts.update_set(sid, {"deleted": True})
    lifts.import_sets(1, SETS)
    assert len(lifts.sessions(30)[0]["sets"]) == 2


def test_manual_set_added_and_counted():
    add_activity()
    lifts.import_sets(1, SETS)
    lifts.add_set(1, "bench press", 5, 60.0)
    names = {e["exercise"] for e in lifts.exercise_history()}
    assert "BENCH_PRESS" in names


def test_validation():
    add_activity()
    lifts.import_sets(1, SETS)
    sid = lifts.sessions(30)[0]["sets"][0]["id"]
    with pytest.raises(ValueError):
        lifts.update_set(sid, {"weight_kg": -5})
    with pytest.raises(KeyError):
        lifts.update_set(9999, {"reps": 3})
    with pytest.raises(KeyError):
        lifts.add_set(555, "x", 1, 1)


def test_e1rm_ignores_high_rep_sets():
    assert lifts.e1rm(50, 20) is None and lifts.e1rm(100, 5) == 116.7


def test_api_roundtrip():
    add_activity()
    lifts.import_sets(1, SETS)
    c = TestClient(app)
    data = c.get("/api/lifts").json()
    sid = data["sessions"][0]["sets"][0]["id"]
    r = c.patch(f"/api/lifts/sets/{sid}", json={"weight_kg": 72.5})
    assert r.status_code == 200 and r.json()["weight_kg"] == 72.5
    assert c.patch("/api/lifts/sets/9999", json={"reps": 1}).status_code == 404
    assert c.patch(f"/api/lifts/sets/{sid}", json={"reps": 9999}).status_code == 400
    assert c.post("/api/lifts/sets", json={"activity_id": 1, "exercise": "Pull up", "reps": 5, "weight_kg": 0}).status_code == 200


def test_coach_summary_is_compact():
    add_activity()
    lifts.import_sets(1, SETS)
    cs = lifts.coach_summary()
    assert cs["exercises"][0]["exercise"] == "Barbell back squat"
    assert cs["exercises"][0]["last_sessions"][0]["top"] == "80.0 kg x 8"
