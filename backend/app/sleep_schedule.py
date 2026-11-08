"""Bedtime and wake-up times for Whoop and Garmin, in local clock time."""
import json
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev

from .db import get_db


def _offset(raw_offset: str | None) -> timedelta:
    if not raw_offset:
        return timedelta(0)
    sign = -1 if raw_offset.startswith("-") else 1
    h, m = raw_offset.lstrip("+-").split(":")
    return sign * timedelta(hours=int(h), minutes=int(m))


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def bed_minutes(dt: datetime) -> int:
    """Minutes since local midnight, with after-midnight bedtimes continuing past 24:00 (01:20 -> 1520)."""
    m = dt.hour * 60 + dt.minute
    return m + 1440 if m < 12 * 60 else m


def wake_minutes(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def clock(minutes: float) -> str:
    m = round(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _night(date: str, bed: datetime, wake: datetime, asleep_s: float | None) -> dict:
    return {
        "date": date,
        "bed": bed.strftime("%H:%M"),
        "wake": wake.strftime("%H:%M"),
        "bed_min": bed_minutes(bed),
        "wake_min": wake_minutes(wake),
        "asleep_h": round(asleep_s / 3600, 2) if asleep_s else None,
        "in_bed_h": round((wake - bed).total_seconds() / 3600, 2),
    }


def whoop_nights(days: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT start, end, raw, light_ms, sws_ms, rem_ms FROM whoop_sleep "
            "WHERE nap = 0 AND end >= datetime('now', ?) ORDER BY start",
            (f"-{days} days",),
        ).fetchall()
    out = []
    for r in rows:
        off = _offset(json.loads(r["raw"]).get("timezone_offset"))
        bed, wake = _parse(r["start"]) + off, _parse(r["end"]) + off
        asleep = ((r["light_ms"] or 0) + (r["sws_ms"] or 0) + (r["rem_ms"] or 0)) / 1000
        out.append(_night(wake.date().isoformat(), bed, wake, asleep))
    return out


def garmin_nights(days: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, start_local, end_local, sleep_s FROM garmin_sleep "
            "WHERE date >= date('now', ?) ORDER BY date",
            (f"-{days} days",),
        ).fetchall()
    return [_night(r["date"], _parse(r["start_local"]), _parse(r["end_local"]), r["sleep_s"]) for r in rows]


def stats(nights: list[dict]) -> dict:
    if not nights:
        return {"nights": 0}
    beds, wakes = [n["bed_min"] for n in nights], [n["wake_min"] for n in nights]
    wk = [n for n in nights if datetime.fromisoformat(n["date"]).weekday() >= 5]  # woke on Sat/Sun
    wd = [n for n in nights if datetime.fromisoformat(n["date"]).weekday() < 5]
    out = {
        "nights": len(nights),
        "avg_bed": clock(mean(beds)),
        "avg_wake": clock(mean(wakes)),
        "bed_sd_min": round(pstdev(beds)),
        "wake_sd_min": round(pstdev(wakes)),
        "avg_asleep_h": round(mean(n["asleep_h"] for n in nights if n["asleep_h"]), 1),
    }
    if wk and wd:
        out["weekday_bed"], out["weekend_bed"] = clock(mean(n["bed_min"] for n in wd)), clock(mean(n["bed_min"] for n in wk))
        out["weekday_wake"], out["weekend_wake"] = clock(mean(n["wake_min"] for n in wd)), clock(mean(n["wake_min"] for n in wk))
    return out


def load(days: int = 90) -> dict:
    w, g = whoop_nights(days), garmin_nights(days)
    dates = sorted({n["date"] for n in w} | {n["date"] for n in g})
    wi, gi = {n["date"]: n for n in w}, {n["date"]: n for n in g}
    return {
        "nights": [{"date": d, "whoop": wi.get(d), "garmin": gi.get(d)} for d in dates],
        "stats": {"whoop": stats(w), "garmin": stats(g)},
    }


def coach_summary(days: int = 90) -> dict:
    d = load(days)
    last = [
        {"date": n["date"], **{k: f'{v["bed"]}-{v["wake"]}' for k, v in (("whoop", n["whoop"]), ("garmin", n["garmin"])) if v}}
        for n in d["nights"][-10:]
    ]
    return {"stats_last_90_days": d["stats"], "last_10_nights_bed_wake": last,
            "note": "Local clock times. SD is night-to-night variability in minutes; smaller is more regular."}
