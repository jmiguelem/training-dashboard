import json
from datetime import date, datetime, timedelta, timezone

from ..db import get_db
from .client import get_client

ACTIVITY_DAYS = 365
DAILY_DAYS = 90
OVERLAP_DAYS = 3


def upsert_activity(conn, a: dict) -> None:
    conn.execute(
        """INSERT INTO garmin_activity (id, name, sport, start, distance_m, duration_s, avg_hr,
             max_hr, avg_speed_ms, calories, cadence, avg_power, elevation_gain_m, vo2max,
             aerobic_te, training_load, raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, sport=excluded.sport,
             start=excluded.start, distance_m=excluded.distance_m, duration_s=excluded.duration_s,
             avg_hr=excluded.avg_hr, max_hr=excluded.max_hr, avg_speed_ms=excluded.avg_speed_ms,
             calories=excluded.calories, cadence=excluded.cadence, avg_power=excluded.avg_power,
             elevation_gain_m=excluded.elevation_gain_m, vo2max=excluded.vo2max,
             aerobic_te=excluded.aerobic_te, training_load=excluded.training_load,
             raw=excluded.raw""",
        (a["activityId"], a.get("activityName"), (a.get("activityType") or {}).get("typeKey"),
         a.get("startTimeGMT") or a.get("startTimeLocal"), a.get("distance"), a.get("duration"),
         a.get("averageHR"), a.get("maxHR"), a.get("averageSpeed"), a.get("calories"),
         a.get("averageRunningCadenceInStepsPerMinute"), a.get("avgPower"),
         a.get("elevationGain"), a.get("vO2MaxValue"), a.get("aerobicTrainingEffect"),
         a.get("activityTrainingLoad"), json.dumps(a)),
    )


def _vo2max(metrics) -> float | None:
    try:
        item = metrics[0] if isinstance(metrics, list) else metrics
        return (item.get("generic") or {}).get("vo2MaxPreciseValue") or (
            item.get("generic") or {}).get("vo2MaxValue")
    except (IndexError, AttributeError, TypeError):
        return None


def upsert_daily(conn, day: str, stats: dict, metrics) -> None:
    conn.execute(
        """INSERT INTO garmin_daily (date, steps, resting_hr, body_battery_high,
             body_battery_low, avg_stress, vo2max, raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET steps=excluded.steps, resting_hr=excluded.resting_hr,
             body_battery_high=excluded.body_battery_high,
             body_battery_low=excluded.body_battery_low, avg_stress=excluded.avg_stress,
             vo2max=excluded.vo2max, raw=excluded.raw""",
        (day, stats.get("totalSteps"), stats.get("restingHeartRate"),
         stats.get("bodyBatteryHighestValue"), stats.get("bodyBatteryLowestValue"),
         stats.get("averageStressLevel"), _vo2max(metrics),
         json.dumps({"stats": stats, "max_metrics": metrics})),
    )


def _last_ok() -> datetime | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT started_at FROM sync_log WHERE source='garmin' AND status='ok' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return datetime.fromisoformat(row["started_at"]) if row else None


def sync_garmin() -> dict:
    api = get_client()
    now = datetime.now(timezone.utc)
    last = _last_ok()
    act_start = (last - timedelta(days=OVERLAP_DAYS)).date() if last else (
        now - timedelta(days=ACTIVITY_DAYS)).date()
    daily_start = (last - timedelta(days=OVERLAP_DAYS)).date() if last else (
        now - timedelta(days=DAILY_DAYS)).date()
    today = now.date()
    with get_db() as conn:
        log_id = conn.execute(
            "INSERT INTO sync_log (source, started_at, status) VALUES ('garmin', ?, 'running')",
            (now.isoformat(),),
        ).lastrowid
    counts = {"activities": 0, "daily": 0}
    try:
        activities = api.get_activities_by_date(act_start.isoformat(), today.isoformat())
        with get_db() as conn:
            for a in activities:
                upsert_activity(conn, a)
        counts["activities"] = len(activities)
        day = daily_start
        while day <= today:
            iso = day.isoformat()
            stats = api.get_stats(iso) or {}
            try:
                metrics = api.get_max_metrics(iso)
            except Exception:
                metrics = None
            with get_db() as conn:
                upsert_daily(conn, iso, stats, metrics)
            counts["daily"] += 1
            day += timedelta(days=1)
    except Exception as exc:
        with get_db() as conn:
            conn.execute(
                "UPDATE sync_log SET finished_at=?, status='error', detail=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), str(exc), log_id),
            )
        raise
    with get_db() as conn:
        conn.execute(
            "UPDATE sync_log SET finished_at=?, status='ok', detail=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), json.dumps(counts), log_id),
        )
    return counts
