import json
from datetime import date

from app.analysis import sport_metrics as sm

RUN = {"averageSpeed": 2.0, "movingDuration": 1800.0, "duration": 1800.0, "distance": 3600.0,
       "averageHR": 150.0, "maxHR": 170.0, "averageRunningCadenceInStepsPerMinute": 150.0,
       "avgStrideLength": 90.0, "avgGroundContactTime": 280.0, "avgVerticalRatio": 8.5,
       "aerobicTrainingEffect": 3.0, "hrTimeInZone_1": 300.0, "hrTimeInZone_2": 900.0,
       "hrTimeInZone_3": 300.0, "hrTimeInZone_4": 300.0, "hrTimeInZone_5": 0.0}
SWIM = {"averageSpeed": 0.9, "movingDuration": 1800.0, "duration": 2400.0, "elapsedDuration": 2400.0,
        "distance": 1600.0, "averageSwolf": 38.0, "avgStrokes": 9.0, "poolLength": 2500.0,
        "averageSwimCadenceInStrokesPerMinute": 20.0, "hrTimeInZone_3": 600.0, "hrTimeInZone_4": 1200.0}


def row(i, sport, start, raw):
    return {"id": i, "sport": sport, "start": start, "raw": json.dumps(raw)}


def test_run_metrics_extracted():
    m = sm.activity_metrics(row(1, "running", "2026-11-01 10:00:00", RUN))
    assert m["group"] == "Run" and m["pace_s_per_km"] == 500
    assert m["cadence_spm"] == 150 and m["stride_m"] == 0.9 and m["ground_contact_ms"] == 280
    assert m["zones"]["z2"] == 15.0


def test_swim_metrics_extracted():
    m = sm.activity_metrics(row(2, "lap_swimming", "2026-11-01 10:00:00", SWIM))
    assert m["pace_s_per_100m"] == 112 and m["swolf"] == 38 and m["pool_m"] == 25
    assert m["rest_share_pct"] == 25


def test_strength_is_ignored_and_slow_run_is_not_a_run():
    assert sm.activity_metrics(row(3, "strength_training", "2026-11-01 10:00:00", {})) is None
    walk = {**RUN, "averageSpeed": 0.2}
    assert sm.activity_metrics(row(4, "treadmill_running", "2026-11-01 10:00:00", walk)) is None


def test_fade_uses_working_laps_only():
    laps = [{"intensityType": "WARMUP", "movingDuration": 120, "averageMovingSpeed": 1.0}] + [
        {"intensityType": "ACTIVE", "movingDuration": 120, "averageMovingSpeed": s} for s in (2.0, 2.0, 1.8, 1.8)
    ]
    assert sm.fade_pct(laps) == -10.0
    assert sm.fade_pct(laps[:3]) is None  # too few laps


def test_weekly_zone_shares_and_trend():
    rows = [
        row(1, "running", "2026-10-26 10:00:00", RUN),
        row(2, "running", "2026-10-28 10:00:00", RUN),
        row(3, "running", "2026-11-03 10:00:00", {**RUN, "averageRunningCadenceInStepsPerMinute": 160.0}),
    ]
    out = sm.build(rows, {}, today=date(2026, 11, 7))["Run"]
    assert [w["sessions"] for w in out["weekly"]] == [2, 1]
    assert out["weekly"][0]["easy_pct"] == 67 and out["weekly"][0]["hard_pct"] == 17
    assert out["trends"]["cadence_spm"]["recent"] == 153.3
    assert out["last_4_weeks"]["sessions"] == 3


def test_coach_summary_drops_empty_sports_and_rows():
    out = sm.build([row(1, "running", "2026-11-01 10:00:00", RUN)], {}, today=date(2026, 11, 7))
    cs = sm.coach_summary(out)
    assert set(cs) == {"Run"} and "activities" not in cs["Run"]
