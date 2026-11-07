import json
from datetime import datetime, timedelta, timezone
from typing import Iterator

import httpx

from .. import config
from ..db import get_db
from .auth import get_access_token

INITIAL_DAYS = 365
OVERLAP_DAYS = 3  # re-fetch recent days; records get revised (scores finalize late)


class NotConnected(Exception):
    pass


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fetch_all(client: httpx.Client, path: str, start: datetime) -> Iterator[dict]:
    params: dict = {"limit": 25, "start": _iso(start)}
    while True:
        resp = client.get(f"{config.WHOOP_API_BASE}{path}", params=params)
        resp.raise_for_status()
        body = resp.json()
        yield from body.get("records", [])
        token = body.get("next_token")
        if not token:
            return
        params["nextToken"] = token


def _score(rec: dict) -> dict:
    return rec.get("score") or {}


def upsert_cycle(conn, r: dict) -> None:
    s = _score(r)
    conn.execute(
        """INSERT INTO whoop_cycle (id, start, end, strain, avg_hr, max_hr, kilojoule, raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET start=excluded.start, end=excluded.end,
             strain=excluded.strain, avg_hr=excluded.avg_hr, max_hr=excluded.max_hr,
             kilojoule=excluded.kilojoule, raw=excluded.raw""",
        (r["id"], r["start"], r.get("end"), s.get("strain"), s.get("average_heart_rate"),
         s.get("max_heart_rate"), s.get("kilojoule"), json.dumps(r)),
    )


def upsert_recovery(conn, r: dict) -> None:
    s = _score(r)
    conn.execute(
        """INSERT INTO whoop_recovery (cycle_id, sleep_id, created_at, recovery_score,
             resting_hr, hrv_rmssd_ms, spo2, skin_temp_c, raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(cycle_id) DO UPDATE SET sleep_id=excluded.sleep_id,
             created_at=excluded.created_at, recovery_score=excluded.recovery_score,
             resting_hr=excluded.resting_hr, hrv_rmssd_ms=excluded.hrv_rmssd_ms,
             spo2=excluded.spo2, skin_temp_c=excluded.skin_temp_c, raw=excluded.raw""",
        (r["cycle_id"], r.get("sleep_id"), r["created_at"], s.get("recovery_score"),
         s.get("resting_heart_rate"), s.get("hrv_rmssd_milli"), s.get("spo2_percentage"),
         s.get("skin_temp_celsius"), json.dumps(r)),
    )


def upsert_sleep(conn, r: dict) -> None:
    s = _score(r)
    st = s.get("stage_summary") or {}
    conn.execute(
        """INSERT INTO whoop_sleep (id, start, end, nap, performance_pct, efficiency_pct,
             respiratory_rate, light_ms, sws_ms, rem_ms, awake_ms, in_bed_ms, disturbances, raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET start=excluded.start, end=excluded.end, nap=excluded.nap,
             performance_pct=excluded.performance_pct, efficiency_pct=excluded.efficiency_pct,
             respiratory_rate=excluded.respiratory_rate, light_ms=excluded.light_ms,
             sws_ms=excluded.sws_ms, rem_ms=excluded.rem_ms, awake_ms=excluded.awake_ms,
             in_bed_ms=excluded.in_bed_ms, disturbances=excluded.disturbances, raw=excluded.raw""",
        (r["id"], r["start"], r["end"], int(bool(r.get("nap"))),
         s.get("sleep_performance_percentage"), s.get("sleep_efficiency_percentage"),
         s.get("respiratory_rate"), st.get("total_light_sleep_time_milli"),
         st.get("total_slow_wave_sleep_time_milli"), st.get("total_rem_sleep_time_milli"),
         st.get("total_awake_time_milli"), st.get("total_in_bed_time_milli"),
         st.get("disturbance_count"), json.dumps(r)),
    )


def upsert_workout(conn, r: dict) -> None:
    s = _score(r)
    conn.execute(
        """INSERT INTO whoop_workout (id, start, end, sport_name, strain, avg_hr, max_hr,
             kilojoule, distance_m, raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET start=excluded.start, end=excluded.end,
             sport_name=excluded.sport_name, strain=excluded.strain, avg_hr=excluded.avg_hr,
             max_hr=excluded.max_hr, kilojoule=excluded.kilojoule,
             distance_m=excluded.distance_m, raw=excluded.raw""",
        (r["id"], r["start"], r["end"], r.get("sport_name"), s.get("strain"),
         s.get("average_heart_rate"), s.get("max_heart_rate"), s.get("kilojoule"),
         s.get("distance_meter"), json.dumps(r)),
    )


RESOURCES = [
    ("cycles", "/cycle", upsert_cycle),
    ("recovery", "/recovery", upsert_recovery),
    ("sleep", "/activity/sleep", upsert_sleep),
    ("workouts", "/activity/workout", upsert_workout),
]


def _sync_start() -> datetime:
    with get_db() as conn:
        row = conn.execute(
            "SELECT started_at FROM sync_log WHERE source='whoop' AND status='ok' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row:
        return datetime.fromisoformat(row["started_at"]) - timedelta(days=OVERLAP_DAYS)
    return datetime.now(timezone.utc) - timedelta(days=INITIAL_DAYS)


def sync_whoop() -> dict:
    token = get_access_token()
    if not token:
        raise NotConnected("Whoop not connected")
    started = datetime.now(timezone.utc)
    start = _sync_start()
    counts: dict[str, int] = {}
    with get_db() as conn:
        log_id = conn.execute(
            "INSERT INTO sync_log (source, started_at, status) VALUES ('whoop', ?, 'running')",
            (started.isoformat(),),
        ).lastrowid
    try:
        with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30) as client:
            for name, path, upsert in RESOURCES:
                n = 0
                for rec in fetch_all(client, path, start):
                    with get_db() as conn:
                        upsert(conn, rec)
                    n += 1
                counts[name] = n
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
