"""Gym sets: imported from Garmin, editable by the user. Edits are never overwritten by sync."""
from collections import defaultdict
from datetime import date, timedelta

from .analysis.metrics import parse_ts
from .db import get_db

MIN_REAL_SET_S = 5  # sets shorter than this usually mean the start button was missed


def pretty(name: str) -> str:
    return name.replace("_", " ").capitalize()


def import_sets(activity_id: int, exercise_sets: list[dict]) -> int:
    """Upsert Garmin ACTIVE sets. Rows the user edited or deleted are left alone."""
    n = 0
    with get_db() as conn:
        for idx, s in enumerate(exercise_sets):
            if s.get("setType") != "ACTIVE":
                continue
            ex = (s.get("exercises") or [{}])[0]
            name = ex.get("name") or ex.get("category") or "UNKNOWN"
            nxt = exercise_sets[idx + 1] if idx + 1 < len(exercise_sets) else None
            rest = nxt.get("duration") if nxt and nxt.get("setType") == "REST" else None
            w = s.get("weight")
            conn.execute(
                """INSERT INTO lift_set (activity_id, set_index, exercise, reps, weight_kg,
                       duration_s, rest_s, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(activity_id, set_index) DO UPDATE SET
                     exercise=excluded.exercise, reps=excluded.reps, weight_kg=excluded.weight_kg,
                     duration_s=excluded.duration_s, rest_s=excluded.rest_s,
                     started_at=excluded.started_at
                   WHERE lift_set.edited = 0 AND lift_set.deleted = 0""",
                (activity_id, idx, name, s.get("repetitionCount"),
                 round(w / 1000, 2) if w else None, s.get("duration"), rest, s.get("startTime")),
            )
            n += 1
    return n


def sync_lifts(api, limit: int = 200) -> int:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT a.id FROM garmin_activity a WHERE a.sport = 'strength_training' "
            "AND NOT EXISTS (SELECT 1 FROM lift_set l WHERE l.activity_id = a.id) "
            "ORDER BY a.start DESC LIMIT ?",
            (limit,),
        ).fetchall()
        recent = conn.execute(
            "SELECT id FROM garmin_activity WHERE sport = 'strength_training' "
            "AND start >= datetime('now', '-4 days')"
        ).fetchall()
    ids = [r["id"] for r in rows] + [r["id"] for r in recent if r["id"] not in {x["id"] for x in rows}]
    total = 0
    for aid in ids:
        try:
            sets = (api.get_activity_exercise_sets(aid) or {}).get("exerciseSets") or []
        except Exception:
            continue
        total += import_sets(aid, sets)
    return total


def is_suspect(row: dict) -> bool:
    return not row["edited"] and (
        not row["reps"] or (row["duration_s"] is not None and row["duration_s"] < MIN_REAL_SET_S)
    )


def e1rm(weight: float | None, reps: int | None) -> float | None:
    """Epley estimate. Not meaningful past ~12 reps, so those return None."""
    if not weight or not reps or reps > 12:
        return None
    return round(weight * (1 + reps / 30), 1)


def _set_row(r) -> dict:
    d = dict(r)
    d["suspect"] = is_suspect(d)
    d["name"] = pretty(d["exercise"])
    d["e1rm"] = e1rm(d["weight_kg"], d["reps"])
    return d


def sessions(days: int = 180) -> list[dict]:
    with get_db() as conn:
        acts = conn.execute(
            "SELECT id, start, name, duration_s, avg_hr FROM garmin_activity "
            "WHERE sport = 'strength_training' AND start >= datetime('now', ?) ORDER BY start DESC",
            (f"-{days} days",),
        ).fetchall()
        sets = conn.execute(
            "SELECT * FROM lift_set WHERE deleted = 0 AND activity_id IN "
            "(SELECT id FROM garmin_activity WHERE sport='strength_training' AND start >= datetime('now', ?)) "
            "ORDER BY activity_id, COALESCE(set_index, 9999), id",
            (f"-{days} days",),
        ).fetchall()
    by_act: dict[int, list] = defaultdict(list)
    for s in sets:
        by_act[s["activity_id"]].append(_set_row(s))
    out = []
    for a in acts:
        ss = by_act.get(a["id"], [])
        good = [s for s in ss if not s["suspect"]]
        out.append(
            {
                "activity_id": a["id"],
                "date": parse_ts(a["start"]).date().isoformat(),
                "name": a["name"],
                "minutes": round((a["duration_s"] or 0) / 60),
                "sets": ss,
                "volume_kg": round(sum((s["weight_kg"] or 0) * (s["reps"] or 0) for s in good)),
                "suspect_sets": sum(1 for s in ss if s["suspect"]),
            }
        )
    return out


def exercise_history(days: int = 365) -> list[dict]:
    """Per exercise: top set and best estimated 1RM per session, oldest first."""
    sess = list(reversed(sessions(days)))
    hist: dict[str, list[dict]] = defaultdict(list)
    for s in sess:
        per: dict[str, list[dict]] = defaultdict(list)
        for st in s["sets"]:
            if not st["suspect"]:
                per[st["exercise"]].append(st)
        for ex, ss in per.items():
            top = max(ss, key=lambda x: ((x["weight_kg"] or 0), (x["reps"] or 0)))
            est = [x["e1rm"] for x in ss if x["e1rm"]]
            hist[ex].append(
                {
                    "date": s["date"],
                    "sets": len(ss),
                    "top_weight_kg": top["weight_kg"],
                    "top_reps": top["reps"],
                    "best_e1rm": max(est) if est else None,
                    "volume_kg": round(sum((x["weight_kg"] or 0) * (x["reps"] or 0) for x in ss)),
                }
            )
    out = []
    for ex, h in hist.items():
        weights = [x["top_weight_kg"] for x in h if x["top_weight_kg"]]
        out.append(
            {
                "exercise": ex,
                "name": pretty(ex),
                "sessions": len(h),
                "last_date": h[-1]["date"],
                "best_weight_kg": max(weights) if weights else None,
                "best_e1rm": max((x["best_e1rm"] for x in h if x["best_e1rm"]), default=None),
                "history": h,
            }
        )
    out.sort(key=lambda e: (-e["sessions"], e["name"]))
    return out


def weekly_volume(days: int = 180) -> list[dict]:
    wk: dict[str, dict] = defaultdict(lambda: {"sessions": 0, "sets": 0, "volume_kg": 0})
    for s in sessions(days):
        d = date.fromisoformat(s["date"])
        key = (d - timedelta(days=d.weekday())).isoformat()
        good = [x for x in s["sets"] if not x["suspect"]]
        wk[key]["sessions"] += 1
        wk[key]["sets"] += len(good)
        wk[key]["volume_kg"] += s["volume_kg"]
    return [{"week": k, **v} for k, v in sorted(wk.items())]


def update_set(set_id: int, fields: dict) -> dict:
    allowed = {"exercise", "reps", "weight_kg", "duration_s", "deleted"}
    upd = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "reps" in upd and not 0 <= int(upd["reps"]) <= 200:
        raise ValueError("reps must be 0-200")
    if "weight_kg" in upd and not 0 <= float(upd["weight_kg"]) <= 1000:
        raise ValueError("weight_kg must be 0-1000")
    if "exercise" in upd:
        upd["exercise"] = str(upd["exercise"]).strip().upper().replace(" ", "_")[:80]
        if not upd["exercise"]:
            raise ValueError("exercise is required")
    if "deleted" in upd:
        upd["deleted"] = int(bool(upd["deleted"]))
    if not upd:
        raise ValueError("nothing to update")
    cols = ", ".join(f"{k} = ?" for k in upd)
    with get_db() as conn:
        cur = conn.execute(f"UPDATE lift_set SET {cols}, edited = 1 WHERE id = ?", (*upd.values(), set_id))
        if cur.rowcount == 0:
            raise KeyError(set_id)
        return _set_row(conn.execute("SELECT * FROM lift_set WHERE id = ?", (set_id,)).fetchone())


def add_set(activity_id: int, exercise: str, reps: int, weight_kg: float) -> dict:
    exercise = exercise.strip().upper().replace(" ", "_")
    if not exercise:
        raise ValueError("exercise is required")
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM garmin_activity WHERE id = ?", (activity_id,)).fetchone():
            raise KeyError(activity_id)
        cur = conn.execute(
            "INSERT INTO lift_set (activity_id, set_index, exercise, reps, weight_kg, source, edited) "
            "VALUES (?, NULL, ?, ?, ?, 'manual', 1)",
            (activity_id, exercise, reps, weight_kg),
        )
        return _set_row(conn.execute("SELECT * FROM lift_set WHERE id = ?", (cur.lastrowid,)).fetchone())


def coach_summary(days: int = 120, max_exercises: int = 12) -> dict:
    """Compact: weekly volume plus the last few top sets for the most-trained exercises."""
    ex = exercise_history(days)[:max_exercises]
    return {
        "weekly_volume": weekly_volume(56),
        "exercises": [
            {
                "exercise": e["name"],
                "sessions": e["sessions"],
                "best_weight_kg": e["best_weight_kg"],
                "best_e1rm_kg": e["best_e1rm"],
                "last_sessions": [
                    {"date": h["date"], "top": f'{h["top_weight_kg"]} kg x {h["top_reps"]}', "sets": h["sets"]}
                    for h in e["history"][-4:]
                ],
            }
            for e in ex
        ],
        "note": "Sets under 5 s or with 0 reps are excluded as probable missed set starts unless the athlete edited them.",
    }
