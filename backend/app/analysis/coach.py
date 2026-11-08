"""Claude-powered coach: weekly review and chat, grounded in the user's own data."""
import json
from datetime import date, datetime, timedelta, timezone

import anthropic

from .. import config
from ..db import get_db
from .. import lifts, plan
from .. import profile as prof
from . import sport_metrics
from .metrics import compute, normalize_sport, parse_ts, sport_group

SYSTEM_TEMPLATE = """\
You are a careful, practical endurance and strength coach for one athlete. You only know what is in the data below. You remember the athlete's goal, profile, earlier chat and your own past recommendations, all given below.

About the athlete:
{profile}
Rules:
- Ground every claim in the numbers provided. Quote the actual values. If data is missing or too thin to conclude, say so.
- Tie advice to the athlete's goal and race date. Say how today's advice moves them toward it.
- Be concise and direct. Plain text only: short paragraphs and simple "-" lists, no markdown headings, no bold, no tables.
- Prioritise injury prevention and gradual progression for a beginner runner (about +10% weekly volume, easy aerobic running, enough rest).
- Whoop recovery under 34 percent is low, 34-66 moderate, 67+ high. Treat HRV and resting HR as trends against the athlete's own baseline, not absolute targets.
- You are not a doctor. For pain, dizziness, chest symptoms or anything that sounds medical, tell them to stop and see a professional.
- Do not invent workouts the data does not support. Suggestions should be concrete (what, how long, how hard) and fit the stated goals.
"""

# Rule-of-thumb readiness targets for a half Ironman (longest single session before race day).
TARGETS = {"Run": 18.0, "Swim": 1.9, "Bike": 80.0}  # km

MAX_ACTIVITIES = 25
DAILY_DAYS = 14


class CoachUnavailable(Exception):
    pass


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def build_context(today: datetime | None = None) -> dict:
    with get_db() as conn:
        acts = _rows(
            conn,
            "SELECT sport, start, distance_m, duration_s, avg_hr, avg_speed_ms, name, "
            "training_load FROM garmin_activity WHERE start >= datetime('now', '-90 days') "
            "ORDER BY start",
        )
        runs_6m = _rows(
            conn,
            "SELECT sport, start, distance_m, duration_s, avg_hr, avg_speed_ms FROM garmin_activity "
            "WHERE start >= datetime('now', '-180 days') AND sport LIKE '%running%' ORDER BY start",
        )
        rec = _rows(
            conn,
            "SELECT created_at, recovery_score, resting_hr, hrv_rmssd_ms FROM whoop_recovery "
            "WHERE created_at >= datetime('now', '-60 days') ORDER BY created_at",
        )
        sl = _rows(
            conn,
            "SELECT end, nap, light_ms, sws_ms, rem_ms, performance_pct FROM whoop_sleep "
            "WHERE end >= datetime('now', '-60 days') ORDER BY end",
        )
        cyc = _rows(
            conn,
            "SELECT start, strain FROM whoop_cycle WHERE start >= datetime('now', '-30 days') "
            "ORDER BY start",
        )
    analysis = compute(acts, rec, sl)

    daily: dict[str, dict] = {}
    cutoff = (today or datetime.now(timezone.utc)).date() - timedelta(days=DAILY_DAYS - 1)
    for r in rec:
        d = parse_ts(r["created_at"]).date()
        if d >= cutoff:
            daily.setdefault(d.isoformat(), {}).update(
                recovery=r["recovery_score"], hrv=_r(r["hrv_rmssd_ms"]), rhr=r["resting_hr"]
            )
    for s in sl:
        d = parse_ts(s["end"]).date()
        if d >= cutoff and not s["nap"]:
            asleep = ((s["light_ms"] or 0) + (s["sws_ms"] or 0) + (s["rem_ms"] or 0)) / 3.6e6
            daily.setdefault(d.isoformat(), {}).update(
                sleep_h=round(asleep, 1), sleep_perf=s["performance_pct"]
            )
    for c in cyc:
        d = parse_ts(c["start"]).date()
        if d >= cutoff:
            daily.setdefault(d.isoformat(), {}).update(strain=_r(c["strain"]))

    def entry(a):
        a = {**a, "sport": normalize_sport(a["sport"], a["avg_speed_ms"])}
        g = sport_group(a["sport"])
        km = (a["distance_m"] or 0) / 1000
        return g, {
            "date": parse_ts(a["start"]).date().isoformat(),
            "type": g,
            "minutes": round((a["duration_s"] or 0) / 60),
            "km": round(km, 2) if km else None,
            "avg_hr": _r(a["avg_hr"]),
            "pace_min_per_km": _pace(a["avg_speed_ms"]) if g == "Run" else None,
        }

    # Every real run (6 months) so the coach sees the whole running history,
    # plus the latest non-run sessions. Runs must not be crowded out by gym sessions.
    runs = [e for g, e in map(entry, runs_6m) if g == "Run"]
    recent = [e for g, e in map(entry, acts) if g != "Run"][-MAX_ACTIVITIES:]
    sm_all = sport_metrics.load(365)
    sm_all_summary = sport_metrics.coach_summary(sm_all)
    cutoff_swim = (today or datetime.now(timezone.utc)).date() - timedelta(days=120)
    swims = [
        {
            "date": a["date"], "km": a["km"], "minutes": a["minutes"], "pace_per_100m_s": a.get("pace_s_per_100m"),
            "swolf": a.get("swolf"), "avg_hr": a["avg_hr"],
        }
        for a in sm_all["Swim"]["activities"]
        if a["date"] >= cutoff_swim.isoformat()
    ]
    return {
        "today": (today or datetime.now(timezone.utc)).date().isoformat(),
        "metrics": analysis["metrics"],
        "flags": analysis["flags"],
        "daily_last_14_days": dict(sorted(daily.items())),
        "sport_metrics": sm_all_summary,
        "all_swims_last_120_days": swims,
        "gym_lifts": lifts.coach_summary(),
        "all_runs_last_6_months": runs,
        "recent_non_run_activities": recent,
    }


def _r(x):
    return None if x is None else round(x)


def _pace(speed_ms):
    if not speed_ms:
        return None
    s = 1000 / speed_ms
    return f"{int(s // 60)}:{int(s % 60):02d}"


def _client() -> anthropic.Anthropic:
    try:
        return anthropic.Anthropic()
    except Exception as exc:  # missing credentials
        raise CoachUnavailable(
            "No Anthropic API key. Add ANTHROPIC_API_KEY to .env and restart the backend."
        ) from exc


def _call(system: str, messages: list[dict], max_tokens: int, schema: dict | None = None) -> str:
    client = _client()
    try:
        resp = client.messages.create(
            model=config.COACH_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": "medium"}
            | ({"format": {"type": "json_schema", "schema": schema}} if schema else {}),
        )
    except anthropic.AuthenticationError as exc:
        raise CoachUnavailable("Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise CoachUnavailable("Anthropic rate limit hit. Try again in a minute.") from exc
    except anthropic.APIConnectionError as exc:
        raise CoachUnavailable("Could not reach the Anthropic API.") from exc
    except anthropic.APIStatusError as exc:
        raise CoachUnavailable(f"Anthropic API error ({exc.status_code}).") from exc
    except Exception as exc:  # credential resolution problems surface as non-API errors
        raise CoachUnavailable(
            "Could not authenticate with Anthropic. Set ANTHROPIC_API_KEY in .env and restart "
            "the backend. (A stale `ant auth` profile on this machine can also cause this.)"
        ) from exc
    if resp.stop_reason == "max_tokens":
        raise CoachUnavailable("The reply was cut off. Try again or ask a shorter question.")
    if resp.stop_reason == "refusal":
        raise CoachUnavailable("The model declined this request. Try rephrasing.")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise CoachUnavailable("The model returned no text. Try again.")
    return text


def _system_with_data(ctx: dict) -> str:
    notes = recent_notes(3)
    notes_txt = ""
    if notes:
        notes_txt = "\nYour own recent recommendations to this athlete (check whether they were followed):\n" + "\n".join(
            f"- {n['week_key']}: {n['text']}" for n in notes
        )
    return (
        SYSTEM_TEMPLATE.format(profile=prof.profile_text())
        + notes_txt
        + "\n\nAthlete data (JSON):\n"
        + json.dumps(ctx, indent=1)
    )


def week_key(today: datetime | None = None) -> str:
    y, w, _ = (today or datetime.now(timezone.utc)).isocalendar()
    return f"{y}-W{w:02d}"


def recent_notes(n: int = 3) -> list[dict]:
    with get_db() as conn:
        rows = _rows(
            conn, "SELECT week_key, created_at, text FROM coach_note ORDER BY id DESC LIMIT ?", (n,)
        )
    return list(reversed(rows))


def weekly_summary(force: bool = False) -> dict:
    """Review + 7-day plan + recommendations for the target week, in one structured call."""
    key = plan.target_week_key()
    if not force:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM coach_summary WHERE week_key = ?", (key,)).fetchone()
        if row and plan.get_plan(key):
            return {**dict(row), "cached": True}
    ctx = build_context()
    ctx["goal_progress"] = goal_progress()
    p = prof.get_profile()
    start = plan.week_start(key)
    today = plan.local_today()
    prompt = (
        f"Write the review and the training plan for the week of Monday {start.isoformat()} to Sunday "
        f"{(start + timedelta(days=6)).isoformat()}. Today is {today.isoformat()}.\n"
        "Fields:\n"
        "- review: under 200 words, plain text. If your recent recommendations are listed above, say whether "
        "the data shows they were followed. Then what is going well, what to watch, and progress toward the "
        "goal and race date (use goal_progress). Quote numbers. End with one sentence on when to stop and see a professional.\n"
        "- focus: one sentence naming the theme of the week.\n"
        "- sessions: one entry per planned session, up to 14. A day may have two sessions (for example a run "
        "and a short gym session) and a day with nothing planned is a rest day. Leave at least one day completely empty as a full rest day. "
        "day is Mon to Sun. sport is run, swim, bike, gym or other. title is short (for example 'Easy run'). "
        "details says how to do it: duration, zone or heart rate range in bpm, structure. "
        f"Plan {p['gym_days_per_week']} gym sessions, as the athlete trains lifting that often; plan fewer only if the data "
        "clearly calls for it, and then say why in the focus. Keep gym sessions short, and keep heavy leg work away from the "
        "day before a run. Never stack two hard sessions in a day or on consecutive days. "
        "duration_min is an integer. intensity is easy, moderate or hard. condition is a concrete "
        "go/no-go rule such as 'Only if Whoop recovery is 34% or higher; otherwise walk or rest', or an empty string. "
        "Always write the full week; days already in the past are removed automatically.\n"
        "- recommendations: 3 to 6 short, specific items such as sleep targets or rules for when to train. "
        "category is sleep, recovery, training, load, nutrition or other. condition is an optional rule, else an empty string.\n"
    )
    system = _system_with_data(ctx)
    messages = [{"role": "user", "content": prompt}]
    data = None
    for attempt in range(2):
        raw = _call(system, messages, 12000, schema=plan.SCHEMA)
        try:
            data = plan.normalize(json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CoachUnavailable("The coach returned an unreadable plan. Try again.") from exc
        if plan.has_rest_day(data) or attempt == 1:
            break
        messages += [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "That plan has a session on every day. Return the whole plan again with at least one "
                "day completely empty as a full rest day. Keep the review, focus and recommendations.",
            },
        ]
    if not data["review"]:
        raise CoachUnavailable("The coach returned an empty review. Try again.")
    plan.drop_past_days(data, start, today)
    now = datetime.now(timezone.utc).isoformat()
    plan.save(key, config.COACH_MODEL, data)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO coach_summary (week_key, created_at, model, text) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(week_key) DO UPDATE SET created_at=excluded.created_at, "
            "model=excluded.model, text=excluded.text",
            (key, now, config.COACH_MODEL, data["review"]),
        )
        conn.execute("DELETE FROM coach_note WHERE week_key = ?", (key,))
        conn.execute(
            "INSERT INTO coach_note (week_key, created_at, text) VALUES (?, ?, ?)",
            (key, now, plan.notes_text(data)),
        )
    return {"week_key": key, "created_at": now, "model": config.COACH_MODEL, "text": data["review"], "cached": False}


def latest_summary() -> dict | None:
    with get_db() as conn:
        for key in (plan.displayed_week_key(), plan.target_week_key()):
            row = conn.execute("SELECT * FROM coach_summary WHERE week_key = ?", (key,)).fetchone()
            if row:
                return {**dict(row), "cached": True}
    return None


def goal_progress(today: date | None = None) -> dict:
    """Longest single session per sport against rule-of-thumb readiness targets, plus run volume."""
    p = prof.get_profile()
    with get_db() as conn:
        rows = _rows(
            conn,
            "SELECT sport, start, distance_m, avg_speed_ms FROM garmin_activity "
            "WHERE start >= datetime('now', '-365 days')",
        )
    best = {"Run": 0.0, "Swim": 0.0, "Bike": 0.0}
    for r in rows:
        g = sport_group(normalize_sport(r["sport"], r["avg_speed_ms"]))
        if g in best:
            best[g] = max(best[g], (r["distance_m"] or 0) / 1000)
    ctx_metrics = compute(
        [{**r, "duration_s": 0, "avg_hr": None} for r in rows if sport_group(r["sport"]) == "Run"],
        [], [], today=today,
    )["metrics"]
    wk = prof.weeks_to_race(p, today)
    items = [
        {
            "sport": g,
            "longest_km": round(best[g], 2),
            "target_km": TARGETS[g],
            "percent": min(100, round(best[g] / TARGETS[g] * 100)),
        }
        for g in ("Run", "Swim", "Bike")
    ]
    return {
        "goal": p["goal"],
        "race_name": p["race_name"],
        "race_date": p["race_date"],
        "weeks_to_race": wk,
        "items": items,
        "run_km_last_4_weeks": ctx_metrics["run_km_4w"],
        "note": "Targets are rule-of-thumb longest-session benchmarks for a half Ironman, not a plan.",
    }


# --- Saved chat -------------------------------------------------------------

HISTORY_LIMIT = 30


def chat_history(limit: int = 200) -> list[dict]:
    with get_db() as conn:
        rows = _rows(
            conn,
            "SELECT role, content, created_at FROM chat_message ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    return list(reversed(rows))


def clear_chat() -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM chat_message")


def chat(message: str) -> str:
    message = message.strip()
    if not message:
        raise ValueError("Message is empty")
    history = [{"role": m["role"], "content": m["content"]} for m in chat_history(HISTORY_LIMIT)]
    while history and history[0]["role"] != "user":
        history.pop(0)
    messages = history + [{"role": "user", "content": message}]
    ctx = build_context()
    ctx["goal_progress"] = goal_progress()
    reply = _call(_system_with_data(ctx), messages, 8000)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO chat_message (role, content, created_at) VALUES (?, ?, ?)",
            [("user", message, now), ("assistant", reply, now)],
        )
    return reply
