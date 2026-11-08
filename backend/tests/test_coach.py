from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.analysis import coach
from app.db import get_db
from app.main import app


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


def test_summary_is_cached_per_week(fake):
    a = coach.weekly_summary()
    assert a["cached"] is False and a["text"] == "All good."
    b = coach.weekly_summary()
    assert b["cached"] is True
    assert len(fake.calls) == 1
    coach.weekly_summary(force=True)
    assert len(fake.calls) == 2


def test_system_prompt_contains_data_and_profile(fake):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO whoop_recovery (cycle_id, created_at, recovery_score, hrv_rmssd_ms, "
            "resting_hr, raw) VALUES (1, datetime('now'), 77, 120.0, 48, '{}')"
        )
    coach.chat("Should I run today?")
    call = fake.calls[0]
    assert "half Ironman" in call["system"].lower() or "half ironman" in call["system"].lower()
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
    assert "190" in fake.calls[0]["system"] and "Z2 114-132" in fake.calls[0]["system"]


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


def test_review_saves_commitments_and_next_week_sees_them(monkeypatch):
    text = "Good week.\nCOMMITMENTS: run twice easy; sleep 7.5 h; one rest day"
    msgs = FakeMessages(text=text)
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=msgs))
    r = coach.weekly_summary()
    assert r["text"] == "Good week."
    notes = coach.recent_notes()
    assert notes[0]["text"] == "run twice easy; sleep 7.5 h; one rest day"
    coach.chat("hello")
    assert "run twice easy" in msgs.calls[-1]["system"]


def test_review_without_commitments_line_still_saves(monkeypatch):
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(text="Fine.")))
    assert coach.weekly_summary()["text"] == "Fine."
    assert coach.recent_notes() == []


def test_goal_progress_tracks_longest_session_per_sport():
    with get_db() as conn:
        for i, (sport, m, spd) in enumerate(
            [("running", 5130, 2.1), ("running", 2240, 2.0), ("lap_swimming", 1000, 0.6),
             ("treadmill_running", 325, 0.2)]
        ):
            conn.execute(
                "INSERT INTO garmin_activity (id, sport, start, distance_m, avg_speed_ms, raw) "
                "VALUES (?, ?, datetime('now', '-10 days'), ?, ?, '{}')", (i + 1, sport, m, spd))
    g = coach.goal_progress()
    by = {i["sport"]: i for i in g["items"]}
    assert by["Run"]["longest_km"] == 5.13 and by["Run"]["percent"] == 28
    assert by["Swim"]["longest_km"] == 1.0 and by["Bike"]["longest_km"] == 0
    assert g["weeks_to_race"] is not None


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
