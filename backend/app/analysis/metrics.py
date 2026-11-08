"""Deterministic training metrics and flags. Pure functions over row dicts."""
from datetime import date, datetime, timedelta, timezone
from statistics import mean

SLEEP_TARGET_H = 8.0


def parse_ts(s: str) -> datetime:
    if s.endswith("Z") or "+" in s[10:]:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    return datetime.fromisoformat(s.replace(" ", "T")).replace(tzinfo=timezone.utc)


WALK_SPEED_MS = 1.4  # below ~11:55 /km a "run" is really walking (slowest real run here: 1.67)


def normalize_sport(sport: str | None, speed_ms: float | None) -> str | None:
    """Garmin sometimes files treadmill walks as runs. Reclassify implausibly slow runs."""
    if sport and "running" in sport and speed_ms is not None and speed_ms < WALK_SPEED_MS:
        return "walking"
    return sport


def sport_group(sport: str | None) -> str:
    s = sport or ""
    if "running" in s:
        return "Run"
    if "swim" in s:
        return "Swim"
    if any(k in s for k in ("cycling", "biking", "ride")):
        return "Bike"
    if "strength" in s:
        return "Strength"
    return "Other"


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return mean(xs) if xs else None


def _pct(new, old):
    if new is None or not old:
        return None
    return (new - old) / old * 100


def _in_window(dt: datetime, today: date, start_ago: int, end_ago: int) -> bool:
    """True if dt's date is within [today-start_ago, today-end_ago] days (inclusive)."""
    d = dt.date()
    return today - timedelta(days=start_ago) <= d <= today - timedelta(days=end_ago)


def compute(activities, recovery, sleep, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    acts = [{**a, "_dt": parse_ts(a["start"]), "_g": sport_group(normalize_sport(a["sport"], a.get("avg_speed_ms")))} for a in activities]
    minutes = lambda xs: sum((a["duration_s"] or 0) for a in xs) / 60  # noqa: E731

    def window(start_ago, end_ago=0):
        return [a for a in acts if _in_window(a["_dt"], today, start_ago, end_ago)]

    last7, prev7 = window(6), window(13, 7)
    last28 = window(27)
    weekly_min = minutes(last7)
    prev_weekly_min = minutes(prev7)
    chronic_weekly = minutes(last28) / 4
    acwr = weekly_min / chronic_weekly if chronic_weekly else None

    # Recovery markers
    rec = [{**r, "_dt": parse_ts(r["created_at"])} for r in recovery]
    r7 = [r for r in rec if _in_window(r["_dt"], today, 6, 0)]
    r30 = [r for r in rec if _in_window(r["_dt"], today, 29, 0)]
    hrv7, hrv30 = _avg(r["hrv_rmssd_ms"] for r in r7), _avg(r["hrv_rmssd_ms"] for r in r30)
    rhr7, rhr30 = _avg(r["resting_hr"] for r in r7), _avg(r["resting_hr"] for r in r30)
    rec7 = _avg(r["recovery_score"] for r in r7)

    # Sleep (non-naps, asleep time)
    sl = [s for s in sleep if not s["nap"]]
    sl7 = [s for s in sl if _in_window(parse_ts(s["end"]), today, 6, 0)]
    asleep_h = [
        ((s["light_ms"] or 0) + (s["sws_ms"] or 0) + (s["rem_ms"] or 0)) / 3_600_000 for s in sl7
    ]
    sleep7 = _avg(asleep_h)

    # Consistency
    session_days = sorted({a["_dt"].date() for a in last28})
    longest_gap = 0
    if session_days:
        pts = session_days + [today]
        longest_gap = max((b - a).days for a, b in zip(pts, pts[1:]))
    days_since_last = (today - session_days[-1]).days if session_days else None

    # Running progress
    runs = sorted([a for a in acts if a["_g"] == "Run"], key=lambda a: a["_dt"])
    run_km_4w = sum((a["distance_m"] or 0) for a in window(27) if a["_g"] == "Run") / 1000
    run_km_prev4w = sum((a["distance_m"] or 0) for a in window(55, 28) if a["_g"] == "Run") / 1000
    eff = [
        a["avg_speed_ms"] * 60 / a["avg_hr"]
        for a in runs
        if a["avg_hr"] and a["avg_speed_ms"] and (a["duration_s"] or 0) >= 600
    ]
    eff_recent = _avg(eff[-4:]) if len(eff) >= 6 else None
    eff_prior = _avg(eff[-8:-4]) if len(eff) >= 8 else None

    metrics = {
        "training_minutes_7d": round(weekly_min),
        "training_minutes_prev_7d": round(prev_weekly_min),
        "load_change_pct": _round(_pct(weekly_min, prev_weekly_min)),
        "acute_chronic_ratio": _round(acwr, 2),
        "sessions_7d": len(last7),
        "sessions_28d": len(last28),
        "days_since_last_session": days_since_last,
        "longest_gap_days_28d": longest_gap,
        "hrv_7d": _round(hrv7),
        "hrv_30d": _round(hrv30),
        "hrv_change_pct": _round(_pct(hrv7, hrv30)),
        "resting_hr_7d": _round(rhr7),
        "resting_hr_30d": _round(rhr30),
        "recovery_7d": _round(rec7),
        "sleep_hours_7d": _round(sleep7, 1),
        "sleep_debt_hours_7d": _round(
            max(0.0, (SLEEP_TARGET_H - sleep7) * 7) if sleep7 is not None else None, 1
        ),
        "run_km_4w": round(run_km_4w, 1),
        "run_km_prev_4w": round(run_km_prev4w, 1),
        "longest_run_km": round(max((a["distance_m"] or 0) for a in runs) / 1000, 2) if runs else 0,
        "run_efficiency_recent": _round(eff_recent, 3),
        "run_efficiency_prior": _round(eff_prior, 3),
        "run_efficiency_change_pct": _round(_pct(eff_recent, eff_prior)),
    }
    return {"metrics": metrics, "flags": flags(metrics, r7)}


def _round(x, n=0):
    if x is None:
        return None
    r = round(x, n)
    return int(r) if n == 0 else r


def flags(m: dict, recent_recovery: list[dict]) -> list[dict]:
    out: list[dict] = []

    def add(level, title, detail):
        out.append({"level": level, "title": title, "detail": detail})

    chg = m["load_change_pct"]
    if chg is not None and m["training_minutes_prev_7d"] >= 60:
        if chg > 30:
            add("warn", "Big load jump", f"Training time is up {chg}% on last week. Aim for 10-20% at a time.")
        elif chg > 10:
            add("info", "Load is climbing", f"Training time is up {chg}% on last week.")
    acr = m["acute_chronic_ratio"]
    if acr is not None and m["sessions_28d"] >= 8:
        if acr > 1.5:
            add("warn", "Acute load far above your norm", f"This week is {acr}x your 4-week average.")
        elif acr < 0.6:
            add("info", "Training dropped off", f"This week is {acr}x your 4-week average.")

    hc = m["hrv_change_pct"]
    if hc is not None and hc <= -10:
        add("warn", "HRV below baseline", f"7-day HRV is {abs(hc)}% under your 30-day average. Consider an easier day.")
    elif hc is not None and hc >= 10:
        add("good", "HRV trending up", f"7-day HRV is {hc}% above your 30-day average.")

    rhr7, rhr30 = m["resting_hr_7d"], m["resting_hr_30d"]
    if rhr7 is not None and rhr30 is not None and rhr7 - rhr30 >= 3:
        add("warn", "Resting HR elevated", f"7-day average {rhr7} bpm vs {rhr30} bpm over 30 days.")

    lows = [r for r in recent_recovery if (r["recovery_score"] or 100) < 34]
    if len(lows) >= 3:
        add("warn", "Several low-recovery days", f"{len(lows)} days under 34% recovery in the last week.")

    debt = m["sleep_debt_hours_7d"]
    if debt is not None and debt >= 7:
        add("warn", "Sleep debt", f"About {debt} h short of {SLEEP_TARGET_H:.0f} h/night this week.")
    elif debt is not None and debt >= 3.5:
        add("info", "Light sleep debt", f"About {debt} h short of {SLEEP_TARGET_H:.0f} h/night this week.")

    if m["days_since_last_session"] is not None and m["days_since_last_session"] >= 4:
        add("info", "Gap in training", f"{m['days_since_last_session']} days since your last session.")
    if m["sessions_7d"] >= 3 and m["sessions_28d"] >= 12:
        add("good", "Consistent", f"{m['sessions_7d']} sessions this week, {m['sessions_28d']} in 4 weeks.")

    ec = m["run_efficiency_change_pct"]
    if ec is not None and ec >= 2:
        add("good", "Running efficiency improving", f"Up {ec}% (speed per heartbeat) over your last 4 runs vs the 4 before.")
    elif ec is not None and ec <= -3:
        add("info", "Running efficiency dipped", f"Down {abs(ec)}% over your last 4 runs vs the 4 before. Fatigue or heat can cause this.")

    if m["run_km_prev_4w"] > 0 and m["run_km_4w"] > m["run_km_prev_4w"] * 1.3:
        add("info", "Run volume rising fast", f"{m['run_km_4w']} km in 4 weeks vs {m['run_km_prev_4w']} km before. Watch for shin and knee niggles.")
    return out
