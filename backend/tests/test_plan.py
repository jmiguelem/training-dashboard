import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import plan, scheduler
from app.analysis import coach
from app.db import get_db
from app.main import app
from tests.test_coach import PLAN_JSON, FakeMessages


def test_target_week_is_next_week_on_sunday_only():
    fri, sat, sun, mon = date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 9)
    assert plan.target_week_key(fri) == "2026-W45"
    assert plan.target_week_key(sat) == "2026-W46"  # the weekend plans the coming week
    assert plan.target_week_key(sun) == "2026-W46"
    assert plan.target_week_key(mon) == "2026-W46"  # Monday: its own week
    assert plan.week_start("2026-W46") == date(2026, 11, 9)


def test_normalize_orders_sessions_and_cleans_fields():
    out = plan.normalize(json.loads(PLAN_JSON))
    assert [x["day"] for x in out["sessions"]] == ["Tue", "Sat"]
    messy = {"review": "x", "focus": "f", "sessions": [
        {"day": "Fri", "sport": "yoga", "title": "t", "details": "", "duration_min": -5, "intensity": "wild", "condition": ""},
        {"day": "Mon", "sport": "run", "title": "A", "details": "", "duration_min": 20, "intensity": "easy", "condition": ""},
        {"day": "Mon", "sport": "gym", "title": "B", "details": "", "duration_min": 30, "intensity": "easy", "condition": ""},
        {"day": "Funday", "sport": "run", "title": "bad day", "details": "", "duration_min": 20, "intensity": "easy", "condition": ""},
        {"day": "Tue", "sport": "run", "title": "  ", "details": "", "duration_min": 20, "intensity": "easy", "condition": ""},
    ], "recommendations": [{"category": "weird", "text": "  ", "condition": ""},
                           {"category": "weird", "text": "Drink water", "condition": ""}]}
    m = plan.normalize(messy)
    assert [(x["day"], x["title"]) for x in m["sessions"]] == [("Mon", "A"), ("Mon", "B"), ("Fri", "t")]
    assert m["sessions"][2]["sport"] == "other" and m["sessions"][2]["duration_min"] == 0
    assert m["sessions"][2]["intensity"] == "easy"
    assert [r["text"] for r in m["recommendations"]] == ["Drink water"]
    assert m["recommendations"][0]["category"] == "other"


def _save(week="2026-W46"):
    plan.save(week, "m", plan.normalize(json.loads(PLAN_JSON)))


def _sessions(p):
    return {x["title"]: x for d in p["days"] for x in d["sessions"]}


def test_plan_auto_matches_activities_and_tracks_checks():
    _save()
    with get_db() as conn:
        conn.execute(  # Tuesday 2026-11-10 run, 25 min
            "INSERT INTO garmin_activity (id, sport, start, distance_m, duration_s, avg_speed_ms, raw) "
            "VALUES (1, 'running', '2026-11-10 15:00:00', 3000, 1500, 2.0, '{}')")
    p = plan.get_plan("2026-W46", today=date(2026, 11, 12))
    assert len(p["days"]) == 7
    run = _sessions(p)["Easy run"]
    assert run["done"] and run["matched"][0]["minutes"] == 25 and run["item"] == "s-0"
    assert p["days"][1]["date"] == "2026-11-10" and p["days"][1]["is_past"]
    assert p["days"][3]["is_today"] is True
    gym = _sessions(p)["Lower body"]
    assert not gym["done"]
    assert p["progress"] == {"done": 1, "total": 2, "recs_done": 0, "recs_total": 2}
    plan.set_check("2026-W46", "s-1", True)
    plan.set_check("2026-W46", "rec-0", True)
    p = plan.get_plan("2026-W46", today=date(2026, 11, 12))
    assert p["progress"]["done"] == 2 and p["progress"]["recs_done"] == 1
    plan.set_check("2026-W46", "s-1", False)
    assert plan.get_plan("2026-W46", today=date(2026, 11, 12))["progress"]["done"] == 1


def test_two_sessions_same_day_each_get_their_own_match():
    data = plan.normalize({"review": "r", "focus": "f", "recommendations": [], "sessions": [
        {"day": "Mon", "sport": "run", "title": "Run A", "details": "", "duration_min": 20, "intensity": "easy", "condition": ""},
        {"day": "Mon", "sport": "gym", "title": "Gym A", "details": "", "duration_min": 40, "intensity": "moderate", "condition": ""},
    ]})
    plan.save("2026-W46", "m", data)
    with get_db() as conn:
        conn.execute("INSERT INTO garmin_activity (id, sport, start, distance_m, duration_s, avg_speed_ms, raw) "
                     "VALUES (1, 'strength_training', '2026-11-09 15:00:00', 0, 2400, NULL, '{}')")
    s = _sessions(plan.get_plan("2026-W46", today=date(2026, 11, 9)))
    assert s["Gym A"]["done"] and not s["Run A"]["done"]
    assert plan.get_plan("2026-W46", today=date(2026, 11, 9))["days"][0]["sessions"][0]["title"] == "Run A"


def test_walk_does_not_count_as_planned_run():
    _save()
    with get_db() as conn:
        conn.execute("INSERT INTO garmin_activity (id, sport, start, distance_m, duration_s, avg_speed_ms, raw) "
                     "VALUES (1, 'treadmill_running', '2026-11-10 15:00:00', 300, 1500, 0.2, '{}')")
    assert not _sessions(plan.get_plan("2026-W46", today=date(2026, 11, 12)))["Easy run"]["done"]


def test_check_validation_and_regenerate_resets_checks():
    _save()
    with pytest.raises(ValueError):
        plan.set_check("2026-W46", "s-99", True)
    with pytest.raises(KeyError):
        plan.set_check("2030-W01", "s-0", True)
    plan.set_check("2026-W46", "rec-1", True)
    _save()
    assert plan.get_plan("2026-W46", today=date(2026, 11, 12))["progress"]["recs_done"] == 0


def test_plan_api(monkeypatch):
    _save(plan.displayed_week_key() or plan.current_week_key())
    c = TestClient(app)
    p = c.get("/api/plan").json()
    assert len(p["days"]) == 7 and p["focus"] == "Build easy aerobic base"
    r = c.put("/api/plan/check", json={"item": "rec-0", "done": True})
    assert r.status_code == 200 and r.json()["progress"]["recs_done"] == 1
    assert c.put("/api/plan/check", json={"item": "nope", "done": True}).status_code == 400
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(text=PLAN_JSON)))
    assert c.post("/api/plan/generate").status_code == 200


def test_displayed_week_falls_back_to_next_week():
    _save("2026-W46")
    assert plan.displayed_week_key(date(2026, 11, 8)) == "2026-W46"  # Sunday, plan written for next week
    assert plan.displayed_week_key(date(2026, 11, 12)) == "2026-W46"
    assert plan.displayed_week_key(date(2026, 11, 20)) is None


def test_plan_api_without_plan():
    assert TestClient(app).get("/api/plan").json()["days"] is None


def test_weekly_job_records_partial_failure(monkeypatch):
    monkeypatch.setattr(scheduler, "sync_whoop", lambda: {"cycles": 3})

    def boom():
        raise RuntimeError("garmin down")

    monkeypatch.setattr(scheduler, "sync_garmin", boom)
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(text=PLAN_JSON)))
    res = scheduler.run_weekly_job()
    assert res["whoop"] == {"cycles": 3} and "error" in res["garmin"] and res["plan"] == "ok"
    with get_db() as conn:
        row = conn.execute("SELECT status FROM sync_log WHERE source='scheduled'").fetchone()
    assert row["status"] == "partial"
    assert plan.get_plan(plan.target_week_key()) is not None


def test_weekly_job_is_not_reentrant():
    assert scheduler._lock.acquire(blocking=False)
    try:
        assert scheduler.run_weekly_job() == {"skipped": "already running"}
    finally:
        scheduler._lock.release()


def test_catch_up_only_when_last_success_is_old():
    assert scheduler._missed_last_run() is False  # never synced: nothing to catch up
    with get_db() as conn:
        conn.execute("INSERT INTO sync_log (source, started_at, status) VALUES ('whoop', '2020-01-01T00:00:00+00:00', 'ok')")
    assert scheduler._missed_last_run() is True
    with get_db() as conn:
        conn.execute("INSERT INTO sync_log (source, started_at, status) "
                     "VALUES ('garmin', datetime('now'), 'ok')")
    assert scheduler._missed_last_run() is False


def test_cron_trigger_is_sunday_night():
    from apscheduler.triggers.cron import CronTrigger

    from app import config

    t = CronTrigger(day_of_week=config.AUTO_SYNC_DAY, hour=config.AUTO_SYNC_HOUR, minute=config.AUTO_SYNC_MINUTE)
    nxt = t.get_next_fire_time(None, __import__("datetime").datetime(2026, 11, 7, 12, 0).astimezone())
    assert nxt.weekday() == 6 and nxt.hour == 23


def test_past_days_are_dropped_not_counted():
    data = plan.normalize(json.loads(PLAN_JSON))  # Tue and Sat
    plan.drop_past_days(data, date(2026, 11, 9), date(2026, 11, 12))  # today is Thursday
    assert [x["title"] for x in data["sessions"]] == ["Lower body"]
    plan.save("2026-W46", "m", data)
    assert plan.get_plan("2026-W46", today=date(2026, 11, 12))["progress"]["total"] == 1


def test_coach_retries_once_when_no_rest_day(monkeypatch):
    full = json.loads(PLAN_JSON)
    full["sessions"] = [{"day": d, "sport": "run", "title": f"Run {d}", "details": "", "duration_min": 20,
                         "intensity": "easy", "condition": ""} for d in plan.DAYS]
    ok = json.loads(PLAN_JSON)
    replies = [json.dumps(full), json.dumps(ok)]

    class Seq(FakeMessages):
        def create(self, **kw):
            self.calls.append(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=replies[len(self.calls) - 1])])

    seq = Seq()
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=seq))
    coach.weekly_summary()
    assert len(seq.calls) == 2 and seq.calls[1]["messages"][-1]["role"] == "user"
    saved = plan.get_plan(plan.target_week_key())
    assert any(not d["sessions"] for d in saved["days"])
