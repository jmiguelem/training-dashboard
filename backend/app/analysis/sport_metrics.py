"""Per-activity and weekly metrics for run, swim and bike, from Garmin raw data."""
import json
from collections import defaultdict
from datetime import timedelta
from statistics import mean

from .metrics import normalize_sport, parse_ts, sport_group

GROUPS = ("Run", "Swim", "Bike")
ZONES = (1, 2, 3, 4, 5)


def _num(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return v
    return None


def _round(x, n=1):
    return None if x is None else round(x, n)


def zone_minutes(raw: dict) -> dict:
    return {f"z{z}": round((raw.get(f"hrTimeInZone_{z}") or 0) / 60, 1) for z in ZONES}


def fade_pct(laps: list[dict]) -> float | None:
    """Speed change from the first half to the second half of the working laps, in percent.
    Negative means slowing down. Needs 4+ laps, so short or one-lap activities return None."""
    work = [
        l for l in laps
        if (l.get("intensityType") or "").upper() not in ("WARMUP", "COOLDOWN", "REST", "RECOVERY")
        and (l.get("movingDuration") or l.get("duration") or 0) >= 30
        and (l.get("averageMovingSpeed") or l.get("averageSpeed"))
    ]
    if len(work) < 4:
        return None
    half = len(work) // 2
    sp = lambda ls: mean((l.get("averageMovingSpeed") or l["averageSpeed"]) for l in ls)  # noqa: E731
    a, b = sp(work[:half]), sp(work[half:])
    return round((b - a) / a * 100, 1) if a else None


def activity_metrics(row: dict, laps: list[dict] | None = None) -> dict | None:
    """row: id, sport, start, raw (JSON str). Returns None for sports we do not analyse."""
    raw = json.loads(row["raw"]) if isinstance(row["raw"], str) else row["raw"]
    group = sport_group(normalize_sport(row["sport"], raw.get("averageSpeed")))
    if group not in GROUPS:
        return None
    moving = _num(raw, "movingDuration", "duration") or 0
    dist = _num(raw, "distance") or 0
    out = {
        "id": row["id"],
        "date": parse_ts(row["start"]).date().isoformat(),
        "group": group,
        "name": raw.get("activityName"),
        "km": round(dist / 1000, 2),
        "minutes": round((_num(raw, "duration") or 0) / 60),
        "moving_minutes": round(moving / 60),
        "avg_hr": _round(_num(raw, "averageHR"), 0),
        "max_hr": _round(_num(raw, "maxHR"), 0),
        "zones": zone_minutes(raw),
        "aerobic_te": _round(_num(raw, "aerobicTrainingEffect")),
        "anaerobic_te": _round(_num(raw, "anaerobicTrainingEffect")),
        "te_label": raw.get("trainingEffectLabel"),
        "training_load": _round(_num(raw, "activityTrainingLoad"), 0),
        "fade_pct": fade_pct(laps or []),
        "laps": len(laps or []) or _num(raw, "lapCount"),
    }
    if group == "Run":
        spd = _num(raw, "averageSpeed")
        out.update(
            pace_s_per_km=round(1000 / spd) if spd else None,
            cadence_spm=_round(_num(raw, "averageRunningCadenceInStepsPerMinute"), 0),
            stride_m=_round((_num(raw, "avgStrideLength") or 0) / 100 or None, 2),
            ground_contact_ms=_round(_num(raw, "avgGroundContactTime"), 0),
            vertical_osc_cm=_round(_num(raw, "avgVerticalOscillation")),
            vertical_ratio=_round(_num(raw, "avgVerticalRatio")),
            elevation_gain_m=_round(_num(raw, "elevationGain"), 0),
            avg_power=_round(_num(raw, "avgPower"), 0),
            gap_s_per_km=round(1000 / g) if (g := _num(raw, "avgGradeAdjustedSpeed")) else None,
        )
    elif group == "Swim":
        pool_cm = _num(raw, "poolLength")
        out.update(
            pace_s_per_100m=round(100 / (dist / moving)) if dist and moving else None,
            swolf=_round(_num(raw, "averageSwolf"), 0),
            strokes_per_length=_round(_num(raw, "avgStrokes")),
            stroke_rate_spm=_round(_num(raw, "averageSwimCadenceInStrokesPerMinute"), 0),
            pool_m=round(pool_cm / 100) if pool_cm else None,
            rest_share_pct=round((1 - moving / _num(raw, "elapsedDuration")) * 100)
            if _num(raw, "elapsedDuration") else None,
        )
    else:  # Bike
        out.update(
            speed_kmh=_round((_num(raw, "averageSpeed") or 0) * 3.6) or None,
            avg_power=_round(_num(raw, "avgPower"), 0),
            norm_power=_round(_num(raw, "normPower"), 0),
            cadence_rpm=_round(_num(raw, "averageBikingCadenceInRevPerMinute"), 0),
            elevation_gain_m=_round(_num(raw, "elevationGain"), 0),
        )
    return out


def week_start(d):
    return d - timedelta(days=d.weekday())


def weekly(acts: list[dict]) -> list[dict]:
    """Per ISO week: sessions, km, minutes, and share of time in easy (Z1-2) vs hard (Z4-5) zones."""
    from datetime import date as _d

    wk: dict = defaultdict(lambda: {"sessions": 0, "km": 0.0, "minutes": 0, "z": {f"z{z}": 0.0 for z in ZONES}})
    for a in acts:
        w = wk[week_start(_d.fromisoformat(a["date"])).isoformat()]
        w["sessions"] += 1
        w["km"] += a["km"]
        w["minutes"] += a["minutes"]
        for k, v in a["zones"].items():
            w["z"][k] += v
    out = []
    for key in sorted(wk):
        w = wk[key]
        tot = sum(w["z"].values())
        out.append(
            {
                "week": key,
                "sessions": w["sessions"],
                "km": round(w["km"], 1),
                "minutes": w["minutes"],
                "zone_minutes": {k: round(v, 1) for k, v in w["z"].items()},
                "easy_pct": round((w["z"]["z1"] + w["z"]["z2"]) / tot * 100) if tot else None,
                "hard_pct": round((w["z"]["z4"] + w["z"]["z5"]) / tot * 100) if tot else None,
            }
        )
    return out


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 1) if xs else None


def trend(acts: list[dict], key: str, n: int = 4) -> dict:
    """Mean of the last n sessions with the metric vs the n before them."""
    vals = [a[key] for a in acts if a.get(key) is not None]
    recent, prior = vals[-n:], vals[-2 * n:-n]
    r, p = _avg(recent), _avg(prior)
    return {"recent": r, "prior": p, "n_recent": len(recent), "n_prior": len(prior)}


TREND_KEYS = {
    "Run": ["pace_s_per_km", "cadence_spm", "stride_m", "ground_contact_ms", "vertical_ratio", "fade_pct", "aerobic_te"],
    "Swim": ["pace_s_per_100m", "swolf", "strokes_per_length", "stroke_rate_spm", "rest_share_pct", "fade_pct", "aerobic_te"],
    "Bike": ["speed_kmh", "avg_power", "norm_power", "cadence_rpm", "fade_pct", "aerobic_te"],
}


def build(rows: list[dict], laps_by_id: dict[int, list[dict]], today=None) -> dict:
    """rows ordered by start ascending."""
    from datetime import date as _d

    today = today or _d.today()
    per: dict[str, list[dict]] = {g: [] for g in GROUPS}
    for r in rows:
        m = activity_metrics(r, laps_by_id.get(r["id"]))
        if m:
            per[m["group"]].append(m)
    out = {}
    for g, acts in per.items():
        four_weeks = [a for a in acts if (today - _d.fromisoformat(a["date"])).days < 28]
        zt = {k: round(sum(a["zones"][k] for a in four_weeks), 1) for k in ("z1", "z2", "z3", "z4", "z5")}
        tot = sum(zt.values())
        out[g] = {
            "activities": acts,
            "weekly": weekly(acts),
            "trends": {k: trend(acts, k) for k in TREND_KEYS[g]},
            "last_4_weeks": {
                "sessions": len(four_weeks),
                "km": round(sum(a["km"] for a in four_weeks), 1),
                "zone_minutes": zt,
                "easy_pct": round((zt["z1"] + zt["z2"]) / tot * 100) if tot else None,
                "hard_pct": round((zt["z4"] + zt["z5"]) / tot * 100) if tot else None,
            },
        }
    return out


def coach_summary(full: dict) -> dict:
    """Compact version for the coach prompt: no per-activity rows, only trends and zone shares."""
    return {
        g: {"last_4_weeks": d["last_4_weeks"], "trends_last_4_vs_prior_4": {
            k: v for k, v in d["trends"].items() if v["recent"] is not None
        }}
        for g, d in full.items()
        if d["activities"]
    }


def load(days: int = 365, today=None) -> dict:
    from ..db import get_db

    with get_db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, sport, start, raw FROM garmin_activity "
                "WHERE start >= datetime('now', ?) ORDER BY start",
                (f"-{days} days",),
            ).fetchall()
        ]
        laps = {
            r["activity_id"]: json.loads(r["data"])
            for r in conn.execute("SELECT activity_id, data FROM garmin_laps").fetchall()
        }
    return build(rows, laps, today)
