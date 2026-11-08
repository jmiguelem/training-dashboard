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
    coach.chat([{"role": "user", "content": "Should I run today?"}])
    call = fake.calls[0]
    assert "half Ironman" in call["system"]
    assert '"recovery": 77' in call["system"]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["messages"][-1]["content"] == "Should I run today?"


def test_chat_requires_trailing_user_message(fake):
    with pytest.raises(ValueError):
        coach.chat([{"role": "assistant", "content": "hi"}])


def test_chat_drops_leading_assistant_turns(fake):
    coach.chat([{"role": "assistant", "content": "hi"}, {"role": "user", "content": "q"}])
    assert fake.calls[0]["messages"][0]["role"] == "user"


def test_refusal_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(stop="refusal")))
    with pytest.raises(coach.CoachUnavailable):
        coach.chat([{"role": "user", "content": "x"}])


def test_missing_key_gives_503(monkeypatch):
    def boom():
        raise coach.CoachUnavailable("No Anthropic API key.")

    monkeypatch.setattr(coach, "_client", boom)
    c = TestClient(app)
    r = c.post("/api/coach/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503 and "API key" in r.json()["detail"]
    assert c.post("/api/coach/summary").status_code == 503


def test_credential_errors_become_unavailable(monkeypatch):
    class Boom:
        def create(self, **kw):
            raise RuntimeError("bad credentials file")

    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=Boom()))
    with pytest.raises(coach.CoachUnavailable, match="ANTHROPIC_API_KEY"):
        coach.chat([{"role": "user", "content": "x"}])


def test_truncated_reply_is_not_returned(monkeypatch):
    monkeypatch.setattr(coach, "_client", lambda: SimpleNamespace(messages=FakeMessages(stop="max_tokens")))
    with pytest.raises(coach.CoachUnavailable, match="cut off"):
        coach.weekly_summary()
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM coach_summary").fetchone()[0] == 0
