"""Athlete profile stored in the database. Edited in the app, sent to the coach every call."""
import json
from datetime import date

from .db import get_db

DEFAULTS: dict = {
    "goal": "Complete a half Ironman (1.9 km swim, 90 km bike, 21.1 km run).",
    "race_name": "Half Ironman",
    "race_date": "2027-11-07",  # approximate: 'in about a year'; edit in the app
    "max_hr": 190,
    "gym_days_per_week": 4,
    "gym_split": "",
    "background": "Zero running experience before this. Building a running base first while keeping gym training.",
    "injuries": "",
    "notes": "",
}

FIELDS = tuple(DEFAULTS)

# What each preset means for planning. A custom split is passed to the coach as typed.
SPLITS = {
    "Upper/Lower": "sessions alternate Upper and Lower body (for example Upper A, Lower A, Upper B, Lower B). "
    "Every gym session is either an upper-body or a lower-body day. Do not plan full-body, push/pull/legs or "
    "single-muscle-group sessions.",
    "Push/Pull/Legs": "sessions rotate Push (chest, shoulders, triceps), Pull (back, biceps) and Legs. "
    "Do not plan upper/lower or full-body sessions.",
    "Full body": "every gym session trains the whole body. Do not split sessions by body part.",
    "Bro split": "each session focuses on one or two muscle groups (for example chest, back, legs, shoulders, arms). "
    "Do not plan full-body or upper/lower sessions.",
}


def get_profile() -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT data FROM athlete_profile WHERE id = 1").fetchone()
    stored = json.loads(row["data"]) if row else {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in FIELDS}}


def save_profile(update: dict) -> dict:
    clean = {k: update[k] for k in FIELDS if k in update}
    if "max_hr" in clean:
        clean["max_hr"] = int(clean["max_hr"])
        if not 120 <= clean["max_hr"] <= 230:
            raise ValueError("max_hr must be between 120 and 230")
    if "gym_days_per_week" in clean:
        clean["gym_days_per_week"] = int(clean["gym_days_per_week"])
        if not 0 <= clean["gym_days_per_week"] <= 7:
            raise ValueError("gym_days_per_week must be 0-7")
    if clean.get("race_date"):
        try:
            date.fromisoformat(clean["race_date"])
        except ValueError as exc:
            raise ValueError("race_date must be YYYY-MM-DD") from exc
    for k in ("goal", "race_name", "gym_split", "background", "injuries", "notes"):
        if k in clean:
            clean[k] = str(clean[k]).strip()[:2000]
    merged = {**get_profile(), **clean}
    with get_db() as conn:
        conn.execute(
            "INSERT INTO athlete_profile (id, data) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (json.dumps(merged),),
        )
    return merged


def zones(max_hr: int) -> list[tuple[str, int, int]]:
    cuts = [0.5, 0.6, 0.7, 0.8, 0.9]
    out = []
    for i, lo in enumerate(cuts):
        hi = max_hr if i == len(cuts) - 1 else round(max_hr * cuts[i + 1]) - 1
        out.append((f"Z{i + 1}", round(max_hr * lo), hi))
    return out


def weeks_to_race(p: dict, today: date | None = None) -> int | None:
    if not p.get("race_date"):
        return None
    days = (date.fromisoformat(p["race_date"]) - (today or date.today())).days
    return max(0, days // 7)


def split_text(split: str) -> str:
    split = (split or "").strip()
    if not split:
        return "No gym split stated; do not assume one."
    desc = SPLITS.get(split)
    return (
        f"The athlete follows a {split} split: {desc} Every planned gym session must follow this split."
        if desc
        else f"The athlete follows this gym split: {split}. Every planned gym session must follow it."
    )


def profile_text(p: dict | None = None, today: date | None = None) -> str:
    p = p or get_profile()
    z = ", ".join(f"{n} {lo}-{hi}" for n, lo, hi in zones(p["max_hr"]))
    wk = weeks_to_race(p, today)
    lines = [
        f"- Goal: {p['goal']}",
        f"- Race: {p['race_name']} on {p['race_date']}"
        + (f" ({wk} weeks away)" if wk is not None else "")
        + ". The date is the athlete's estimate.",
        f"- Background: {p['background']}",
        f"- Gym: about {p['gym_days_per_week']} sessions a week. " + split_text(p["gym_split"]),
        f"- Max heart rate: {p['max_hr']} bpm (stated by the athlete). Zones in bpm: {z}. "
        "Easy running should sit in Z2, at most the low end of Z3.",
        f"- Injuries or limits: {p['injuries'] or 'none reported'}",
    ]
    if p["notes"]:
        lines.append(f"- Preferences and other notes: {p['notes']}")
    lines.append("- Devices: Garmin watch (activities), Whoop (recovery, sleep, strain).")
    return "\n".join(lines) + "\n"
