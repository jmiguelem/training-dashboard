"""Weekly training plan from the coach: storage, week maths, check-off and auto-matching."""
import json
from datetime import date, datetime, timedelta

from .analysis.metrics import normalize_sport, parse_ts, sport_group
from .db import get_db

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SESSION_SPORTS = ["run", "swim", "bike", "gym", "other"]
INTENSITIES = ["easy", "moderate", "hard"]
CATEGORIES = ["sleep", "recovery", "training", "load", "nutrition", "other"]
SPORT_GROUP = {"run": "Run", "swim": "Swim", "bike": "Bike", "gym": "Strength"}

SCHEMA = {
    "type": "object",
    "properties": {
        "review": {"type": "string"},
        "focus": {"type": "string"},
        "sessions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "string", "enum": DAYS},
                    "sport": {"type": "string", "enum": SESSION_SPORTS},
                    "title": {"type": "string"},
                    "details": {"type": "string"},
                    "duration_min": {"type": "integer"},
                    "intensity": {"type": "string", "enum": ["easy", "moderate", "hard"]},
                    "condition": {"type": "string"},
                },
                "required": ["day", "sport", "title", "details", "duration_min", "intensity", "condition"],
                "additionalProperties": False,
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": CATEGORIES},
                    "text": {"type": "string"},
                    "condition": {"type": "string"},
                },
                "required": ["category", "text", "condition"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["review", "focus", "sessions", "recommendations"],
    "additionalProperties": False,
}


def week_key_of(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_start(key: str) -> date:
    y, w = key.split("-W")
    return date.fromisocalendar(int(y), int(w), 1)


def local_today() -> date:
    return datetime.now().astimezone().date()


def current_week_key(today: date | None = None) -> str:
    return week_key_of(today or local_today())


def target_week_key(today: date | None = None) -> str:
    """The week a new plan is for: next week when generated on Saturday or Sunday, otherwise this week."""
    t = today or local_today()
    return week_key_of(t + timedelta(days=7 - t.weekday())) if t.weekday() >= 5 else week_key_of(t)


def displayed_week_key(today: date | None = None) -> str | None:
    """This week's plan if there is one, else next week's (written on the weekend)."""
    t = today or local_today()
    with get_db() as conn:
        for key in (week_key_of(t), week_key_of(t + timedelta(days=7))):
            if conn.execute("SELECT 1 FROM weekly_plan WHERE week_key = ?", (key,)).fetchone():
                return key
    return None


MAX_SESSIONS = 14


def normalize(raw: dict) -> dict:
    """Coerce model output: valid fields, sessions ordered by day (stable), at most 14. Rest days are implicit."""
    sessions = []
    for d in raw.get("sessions", []):
        if d.get("day") not in DAYS or not str(d.get("title", "")).strip():
            continue
        sessions.append(
            {
                "day": d["day"],
                "sport": d["sport"] if d.get("sport") in SESSION_SPORTS else "other",
                "title": str(d["title"]).strip()[:120],
                "details": str(d.get("details", "")).strip()[:600],
                "duration_min": max(0, int(d.get("duration_min") or 0)),
                "intensity": d["intensity"] if d.get("intensity") in INTENSITIES else "easy",
                "condition": str(d.get("condition", "")).strip()[:300],
            }
        )
    sessions.sort(key=lambda x: DAYS.index(x["day"]))
    recs = [
        {
            "category": r["category"] if r.get("category") in CATEGORIES else "other",
            "text": str(r.get("text", "")).strip()[:300],
            "condition": str(r.get("condition", "")).strip()[:300],
        }
        for r in raw.get("recommendations", [])
        if str(r.get("text", "")).strip()
    ][:8]
    return {
        "review": str(raw.get("review", "")).strip(),
        "focus": str(raw.get("focus", "")).strip()[:300],
        "sessions": sessions[:MAX_SESSIONS],
        "recommendations": recs,
    }


def has_rest_day(data: dict) -> bool:
    return len({x["day"] for x in data["sessions"]}) < 7


def drop_past_days(data: dict, start: date, today: date) -> None:
    """Days already over cannot be planned: remove their sessions so they are not counted as missed."""
    data["sessions"] = [
        x for x in data["sessions"] if start + timedelta(days=DAYS.index(x["day"])) >= today
    ]


def save(week_key: str, model: str, data: dict) -> None:
    now = datetime.now().astimezone().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO weekly_plan (week_key, created_at, model, data) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(week_key) DO UPDATE SET created_at=excluded.created_at, "
            "model=excluded.model, data=excluded.data",
            (week_key, now, model, json.dumps(data)),
        )
        conn.execute("DELETE FROM plan_check WHERE week_key = ?", (week_key,))


def notes_text(data: dict) -> str:
    plan = "; ".join(f"{d['day']} {d['title']}" for d in data["sessions"])
    recs = "; ".join(
        r["text"] + (f" ({r['condition']})" if r["condition"] else "") for r in data["recommendations"]
    )
    return f"Focus: {data['focus']}. Plan: {plan}. Recommendations: {recs}"


def set_check(week_key: str, item: str, done: bool) -> None:
    ok = (item.startswith("s-") and item[2:].isdigit() and int(item[2:]) < MAX_SESSIONS) or (
        item.startswith("rec-") and item[4:].isdigit() and int(item[4:]) < 8
    )
    if not ok:
        raise ValueError("Unknown plan item")
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM weekly_plan WHERE week_key = ?", (week_key,)).fetchone():
            raise KeyError(week_key)
        conn.execute(
            "INSERT INTO plan_check (week_key, item, done) VALUES (?, ?, ?) "
            "ON CONFLICT(week_key, item) DO UPDATE SET done = excluded.done",
            (week_key, item, int(done)),
        )


def _activities_by_date(start: date, end: date) -> dict[str, list[dict]]:
    lo = (start - timedelta(days=1)).isoformat()
    hi = (end + timedelta(days=2)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT sport, start, duration_s, distance_m, avg_speed_ms FROM garmin_activity "
            "WHERE start >= ? AND start < ?",
            (lo, hi),
        ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        day = parse_ts(r["start"]).astimezone().date()
        if not start <= day <= end:
            continue
        out.setdefault(day.isoformat(), []).append(
            {
                "type": sport_group(normalize_sport(r["sport"], r["avg_speed_ms"])),
                "minutes": round((r["duration_s"] or 0) / 60),
                "km": round((r["distance_m"] or 0) / 1000, 2),
            }
        )
    return out


def get_plan(week_key: str | None = None, today: date | None = None) -> dict | None:
    today = today or local_today()
    key = week_key or displayed_week_key(today)
    if not key:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT * FROM weekly_plan WHERE week_key = ?", (key,)).fetchone()
        checks = {
            r["item"]: bool(r["done"])
            for r in conn.execute("SELECT item, done FROM plan_check WHERE week_key = ?", (key,)).fetchall()
        }
    if not row:
        return None
    data = json.loads(row["data"])
    if "sessions" not in data:
        return None
    start = week_start(key)
    acts = _activities_by_date(start, start + timedelta(days=6))
    sessions = []
    for i, x in enumerate(data["sessions"]):
        sessions.append({**x, "item": f"s-{i}", "checked": checks.get(f"s-{i}", False)})
    days = []
    for di, name in enumerate(DAYS):
        dt = start + timedelta(days=di)
        todays = [x for x in sessions if x["day"] == name]
        pool = {g: [a for a in acts.get(dt.isoformat(), []) if a["type"] == g] for g in SPORT_GROUP.values()}
        for x in todays:  # k-th planned session of a sport takes the k-th logged activity of that sport
            group = SPORT_GROUP.get(x["sport"])
            hit = pool[group].pop(0) if group and pool.get(group) else None
            x["matched"] = [hit] if hit else []
            x["done"] = x["checked"] or bool(hit)
        days.append(
            {
                "day": name,
                "date": dt.isoformat(),
                "is_today": dt == today,
                "is_past": dt < today,
                "sessions": todays,
            }
        )
    recs = [
        {**r, "item": f"rec-{i}", "checked": checks.get(f"rec-{i}", False)}
        for i, r in enumerate(data["recommendations"])
    ]
    return {
        "week_key": key,
        "week_start": start.isoformat(),
        "created_at": row["created_at"],
        "model": row["model"],
        "focus": data["focus"],
        "days": days,
        "recommendations": recs,
        "progress": {
            "done": sum(1 for x in sessions if x["done"]),
            "total": len(sessions),
            "recs_done": sum(1 for r in recs if r["checked"]),
            "recs_total": len(recs),
        },
    }
