from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.analysis import coach
from app.db import get_db
from app.main import app


import json as _json

PLAN_JSON = _json.dumps({
    "review": "Good week.", "focus": "Build easy aerobic base",
    "sessions": [
        {"day": "Tue", "sport": "run", "title": "Easy run", "details": "25 min Z2", "duration_min": 25,
         "intensity": "easy", "condition": "Only if recovery is 34% or higher"},
        {"day": "Sat", "sport": "gym", "title": "Lower body", "details": "45 min", "duration_min": 45,
         "intensity": "moderate", "condition": ""},
    ],
    "recommendations": [
        {"category": "sleep", "text": "Sleep 7.5 h", "condition": ""},
        {"category": "training", "text": "Run only when recovery allows", "condition": "recovery 34%+"},
    ],
})


class FakeMessages:
    def __init__(self, text="All good.", stop="end_turn"):
        self.calls = []
        self.text, self.stop = text, stop

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)]
        )


@pytest.fixture
def fake(monkeypatch):
    msgs = FakeMessages()
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=msgs))
    return msgs


def test_summary_is_cached_per_week(monkeypatch):
    fake = FakeMessages(text=PLAN_JSON)
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=fake))
    a = coach.weekly_summary()
    assert a["cached"] is False and a["text"] == "Good week."
    b = coach.weekly_summary()
    assert b["cached"] is True
    assert len(fake.calls) == 1
    coach.weekly_summary(force=True)
    assert len(fake.calls) == 2


def test_system_prompt_contains_data_and_profile(fake):
    from app import profile

    profile.save_profile({"goal_type": "triathlon", "goal": "Finish a half Ironman", "race_date": "2030-01-01"})
    with get_db() as conn:
        conn.execute(
            "INSERT INTO whoop_recovery (cycle_id, created_at, recovery_score, hrv_rmssd_ms, "
            "resting_hr, raw) VALUES (1, datetime('now'), 77, 120.0, 48, '{}')"
        )
    coach.chat("Should I run today?")
    call = fake.calls[0]
    assert "half ironman" in call["system"].lower() and "70.3" in call["system"]
    assert '"recovery": 77' in call["system"]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["messages"][-1]["content"] == "Should I run today?"


def test_chat_rejects_empty_message(fake):
    with pytest.raises(ValueError):
        coach.chat("   ")


def test_chat_is_saved_and_replayed_next_turn(fake):
    coach.chat("first question")
    assert [m["role"] for m in coach.chat_history()] == ["user", "assistant"]
    coach.chat("follow up")
    sent = fake.calls[1]["messages"]
    assert [m["content"] for m in sent] == ["first question", "All good.", "follow up"]
    coach.clear_chat()
    assert coach.chat_history() == []


def test_failed_chat_is_not_saved(monkeypatch):
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(stop="refusal")))
    with pytest.raises(coach.CoachUnavailable):
        coach.chat("x")
    assert coach.chat_history() == []


def test_refusal_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(stop="refusal")))
    with pytest.raises(coach.CoachUnavailable):
        coach.chat("x")


def test_missing_key_gives_503(monkeypatch):
    def boom():
        raise coach.CoachUnavailable("No Anthropic API key.")

    monkeypatch.setattr(coach, "_client", boom)
    c = TestClient(app)
    r = c.post("/api/coach/chat", json={"message": "hi"})
    assert r.status_code == 503 and "API key" in r.json()["detail"]
    assert c.post("/api/coach/summary").status_code == 503


def test_credential_errors_become_unavailable(monkeypatch):
    class Boom:
        def create(self, **kw):
            raise RuntimeError("bad credentials file")

    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=Boom()))
    with pytest.raises(coach.CoachUnavailable, match="ANTHROPIC_API_KEY"):
        coach.chat("x")


def test_truncated_reply_is_not_returned(monkeypatch):
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(stop="max_tokens")))
    with pytest.raises(coach.CoachUnavailable, match="cut off"):
        coach.weekly_summary()
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM coach_summary").fetchone()[0] == 0


def test_old_runs_are_not_crowded_out_by_recent_gym_sessions(fake):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO garmin_activity (id, sport, start, distance_m, duration_s, avg_hr, "
            "avg_speed_ms, raw) VALUES (1, 'running', datetime('now', '-60 days'), 5000, 2400, "
            "154, 2.1, '{}')"
        )
        for i in range(2, 40):
            conn.execute(
                "INSERT INTO garmin_activity (id, sport, start, duration_s, avg_hr, raw) "
                "VALUES (?, 'strength_training', datetime('now', ?), 3600, 120, '{}')",
                (i, f"-{i % 20} hours"),
            )
    ctx = coach.build_context()
    assert len(ctx["all_runs_last_6_months"]) == 1
    assert ctx["all_runs_last_6_months"][0]["avg_hr"] == 154
    assert all(a["type"] != "Run" for a in ctx["recent_non_run_activities"])


def test_profile_includes_max_hr_and_zones(fake):
    coach.chat("zones?")
    assert "185" in fake.calls[0]["system"] and "Z2 111-129" in fake.calls[0]["system"]


def test_profile_edit_reaches_coach_prompt(fake):
    from app import profile

    profile.save_profile({"goal": "Run a sub-2h half marathon", "injuries": "left knee", "max_hr": 200})
    coach.chat("hi")
    sys_prompt = fake.calls[0]["system"]
    assert "sub-2h half marathon" in sys_prompt and "left knee" in sys_prompt
    assert "Z2 120-139" in sys_prompt


def test_profile_validation():
    from app import profile

    with pytest.raises(ValueError):
        profile.save_profile({"max_hr": 50})
    with pytest.raises(ValueError):
        profile.save_profile({"race_date": "next year"})


def test_weeks_to_race():
    from datetime import date

    from app import profile

    p = {**profile.DEFAULTS, "race_date": "2027-11-07"}
    assert profile.weeks_to_race(p, date(2026, 11, 7)) == 52
    assert profile.weeks_to_race({**p, "race_date": "2020-01-01"}, date(2026, 11, 7)) == 0


def test_review_saves_plan_and_notes_and_chat_sees_them(monkeypatch):
    msgs = FakeMessages(text=PLAN_JSON)
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=msgs))
    r = coach.weekly_summary()
    assert r["text"] == "Good week."
    assert msgs.calls[0]["output_config"]["format"]["type"] == "json_schema"
    notes = coach.recent_notes()
    assert "Build easy aerobic base" in notes[0]["text"] and "Sleep 7.5 h" in notes[0]["text"]
    coach.chat("hello")
    assert "Sleep 7.5 h" in msgs.calls[-1]["system"]


def test_unreadable_plan_is_not_saved(monkeypatch):
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(text="not json")))
    with pytest.raises(coach.CoachUnavailable, match="unreadable"):
        coach.weekly_summary()
    assert coach.latest_summary() is None


def test_goal_progress_counts_recent_sessions_not_old_bests():
    from app import profile

    profile.save_profile({"goal_type": "triathlon", "race_date": "2030-01-01"})
    with get_db() as conn:
        for i, (sport, m, spd, days) in enumerate(
            [("running", 5130, 2.1, 10), ("running", 2240, 2.0, 12), ("lap_swimming", 1000, 0.6, 10),
             ("lap_swimming", 4580, 0.85, 110), ("treadmill_running", 325, 0.2, 10)]
        ):
            conn.execute(
                "INSERT INTO garmin_activity (id, sport, start, distance_m, avg_speed_ms, raw) "
                "VALUES (?, ?, datetime('now', ?), ?, ?, '{}')", (i + 1, sport, f"-{days} days", m, spd))
    g = coach.goal_progress()
    by = {i["sport"]: i for i in g["items"]}
    assert by["Run"]["longest_recent_km"] == 5.13 and by["Run"]["percent"] == 28
    swim = by["Swim"]
    assert swim["longest_recent_km"] == 1.0 and swim["percent"] == 53  # the 4.58 km swim is 110 days old
    assert swim["best_12m_km"] == 4.58 and swim["weeks_since_best"] in (15, 16)
    assert by["Bike"]["longest_recent_km"] == 0 and by["Bike"]["best_12m_date"] is None
    assert g["weeks_to_race"] is not None and "last 8 weeks" in g["note"]


def test_phase_by_weeks_to_race():
    assert [coach.phase_for(w) for w in (None, 0, 2, 8, 12, 17)] == [
        None, "race week", "taper", "peak and race-specific", "build", "base"]


def test_recovery_week_suggested_after_three_rising_weeks():
    from datetime import timedelta

    from app import plan as _plan

    monday = _plan.local_today() - timedelta(days=_plan.local_today().weekday())
    with get_db() as conn:
        for i, (weeks_back, minutes) in enumerate([(4, 100), (3, 150), (2, 200), (1, 260)]):
            day = monday - timedelta(weeks=weeks_back) + timedelta(days=2)
            conn.execute("INSERT INTO garmin_activity (id, sport, start, duration_s, raw) "
                         "VALUES (?, 'strength_training', ?, ?, '{}')", (i + 1, f"{day} 15:00:00", minutes * 60))
    g = coach.goal_progress()
    assert g["weekly_training_minutes_last_4_full_weeks"] == [100, 150, 200, 260]
    assert g["recovery_week_suggested"] is True


def test_fresh_profile_has_no_personal_values(fake, monkeypatch):
    from app import profile

    p = profile.get_profile()
    assert p["goal_type"] == "general" and not p["goal"] and not p["race_date"] and not p["background"]
    coach.chat("hi")
    sys_prompt = fake.calls[0]["system"]
    assert "ironman" not in sys_prompt.lower() and "70.3" not in sys_prompt
    assert "No event date set" in sys_prompt
    g = coach.goal_progress()
    assert g["items"] == [] and g["weeks_to_race"] is None


def test_custom_targets_and_goal_type():
    from app import profile

    profile.save_profile({"goal_type": "running", "target_run_km": 21.1})
    g = coach.goal_progress()
    assert [i["sport"] for i in g["items"]] == ["Run"] and g["items"][0]["target_km"] == 21.1
    with pytest.raises(ValueError):
        profile.save_profile({"goal_type": "curling"})
    with pytest.raises(ValueError):
        profile.save_profile({"target_run_km": -3})


def test_seed_file_prefills_profile(tmp_path, monkeypatch):
    from app import config, profile

    seed = tmp_path / "profile.json"
    seed.write_text('{"goal": "Seeded", "max_hr": 177, "bogus": 1}')
    monkeypatch.setattr(config, "PROFILE_SEED", seed)
    p = profile.get_profile()
    assert p["goal"] == "Seeded" and p["max_hr"] == 177 and "bogus" not in p
    profile.save_profile({"goal": "Saved"})
    assert profile.get_profile()["goal"] == "Saved"


def test_knowledge_is_in_every_prompt(fake):
    coach.chat("hi")
    sys_prompt = fake.calls[0]["system"]
    assert "Periodization" in sys_prompt and "80 percent" in sys_prompt and "Maffetone" in sys_prompt



def test_coach_sees_individual_swims(fake):
    import json as _json

    raw = _json.dumps({"averageSpeed": 0.9, "movingDuration": 3600.0, "duration": 4000.0, "distance": 3200.0,
                       "averageHR": 150.0, "averageSwolf": 40.0})
    with get_db() as conn:
        conn.execute(
            "INSERT INTO garmin_activity (id, sport, start, distance_m, duration_s, raw) "
            "VALUES (1, 'lap_swimming', datetime('now', '-20 days'), 3200, 4000, ?)", (raw,))
    ctx = coach.build_context()
    assert ctx["all_swims_last_120_days"][0]["km"] == 3.2


def test_gym_split_reaches_prompt_and_rotation_context(fake):
    from app import lifts, profile

    profile.save_profile({"gym_split": "Upper/Lower", "gym_days_per_week": 4})
    with get_db() as conn:
        conn.execute("INSERT INTO garmin_activity (id, sport, start, name, duration_s, raw) "
                     "VALUES (1, 'strength_training', datetime('now', '-2 days'), 'LOWER 2', 3000, '{}')")
    lifts.import_sets(1, [{"setType": "ACTIVE", "exercises": [{"name": "BARBELL_BACK_SQUAT"}],
                           "repetitionCount": 8, "weight": 70000, "duration": 40}])
    coach.chat("plan?")
    sys_prompt = fake.calls[0]["system"]
    assert "follows a Upper/Lower split" in sys_prompt and "Do not plan full-body" in sys_prompt
    assert "LOWER 2" in sys_prompt and "Barbell back squat" in sys_prompt


def test_custom_split_is_passed_as_typed_and_unset_is_not_assumed():
    from app import profile

    assert "No gym split stated" in profile.split_text("")
    assert "Arnold split" in profile.split_text("Arnold split")
    assert "Push/Pull/Legs" in profile.profile_text({**profile.DEFAULTS, "gym_split": "Push/Pull/Legs", "gym_days_per_week": 3})


def test_profile_api_saves_gym_split():
    c = TestClient(app)
    r = c.put("/api/profile", json={"gym_split": "Push/Pull/Legs"})
    assert r.status_code == 200 and r.json()["gym_split"] == "Push/Pull/Legs"
    assert c.get("/api/profile").json()["gym_split"] == "Push/Pull/Legs"


def test_profile_api_goal_type_and_clearing_targets():
    c = TestClient(app)
    r = c.put("/api/profile", json={"goal_type": "cycling", "target_bike_km": 100})
    assert r.status_code == 200 and r.json()["target_bike_km"] == 100
    assert c.put("/api/profile", json={"goal": "Gran fondo"}).json()["target_bike_km"] == 100
    assert c.put("/api/profile", json={"target_bike_km": None}).json()["target_bike_km"] is None
    assert c.put("/api/profile", json={"goal_type": "curling"}).status_code == 400
