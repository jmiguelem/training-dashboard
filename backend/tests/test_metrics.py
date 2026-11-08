from datetime import date, datetime, timedelta, timezone

from app.analysis.metrics import compute, parse_ts, sport_group

TODAY = date(2026, 11, 7)


def act(days_ago, minutes=60, sport="running", km=5.0, hr=150.0, speed=2.8):
    d = datetime(2026, 11, 7, 12, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return {"sport": sport, "start": d.strftime("%Y-%m-%d %H:%M:%S"), "distance_m": km * 1000,
            "duration_s": minutes * 60, "avg_hr": hr, "avg_speed_ms": speed}


def rec(days_ago, score=70, hrv=100.0, rhr=50):
    d = datetime(2026, 11, 7, 9, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return {"created_at": d.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "recovery_score": score,
            "hrv_rmssd_ms": hrv, "resting_hr": rhr}


def sleep(days_ago, hours=8.0):
    d = datetime(2026, 11, 7, 7, tzinfo=timezone.utc) - timedelta(days=days_ago)
    ms = int(hours * 3_600_000)
    return {"end": d.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "nap": 0,
            "light_ms": ms // 2, "sws_ms": ms // 4, "rem_ms": ms // 4}


def titles(result):
    return {f["title"] for f in result["flags"]}


def test_parse_ts_formats():
    assert parse_ts("2026-11-05 12:00:00").hour == 12
    assert parse_ts("2026-11-05T12:00:00.000Z").tzinfo is not None


def test_sport_group():
    assert sport_group("treadmill_running") == "Run"
    assert sport_group("lap_swimming") == "Swim"
    assert sport_group("strength_training") == "Strength"


def test_big_load_jump_flagged():
    acts = [act(d, 60) for d in (8, 10, 12)] + [act(d, 60) for d in (0, 1, 2, 3, 4, 5)]
    r = compute(acts, [], [], today=TODAY)
    assert r["metrics"]["training_minutes_7d"] == 360
    assert r["metrics"]["training_minutes_prev_7d"] == 180
    assert r["metrics"]["load_change_pct"] == 100
    assert "Big load jump" in titles(r)


def test_hrv_drop_and_sleep_debt():
    recs = [rec(d, hrv=70.0) for d in range(0, 7)] + [rec(d, hrv=100.0) for d in range(7, 30)]
    sl = [sleep(d, hours=6.0) for d in range(0, 7)]
    r = compute([], recs, sl, today=TODAY)
    assert r["metrics"]["hrv_change_pct"] < -10
    assert r["metrics"]["sleep_debt_hours_7d"] == 14.0
    assert {"HRV below baseline", "Sleep debt"} <= titles(r)


def test_empty_data_has_no_flags_and_no_crash():
    r = compute([], [], [], today=TODAY)
    assert r["flags"] == []
    assert r["metrics"]["sessions_7d"] == 0
    assert r["metrics"]["hrv_7d"] is None


def test_run_efficiency_improving():
    old = [act(40 - i, speed=2.5, hr=150.0) for i in range(4)]
    mid = [act(30 - i, speed=2.5, hr=150.0) for i in range(4)]
    new = [act(10 - i, speed=2.9, hr=150.0) for i in range(4)]
    r = compute(old + mid + new, [], [], today=TODAY)
    assert r["metrics"]["run_efficiency_change_pct"] > 2
    assert "Running efficiency improving" in titles(r)
