from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import config, lifts, plan, profile, scheduler, sleep_schedule
from .db import get_db, init_db
from .analysis import coach
from .garmin.client import GarminNotLoggedIn
from .garmin.sync import sync_garmin
from .whoop import auth as whoop_auth
from .whoop.sync import NotConnected, sync_whoop


@asynccontextmanager
async def lifespan(app_: FastAPI):
    init_db()
    app_.state.scheduler = scheduler.start()
    yield
    if app_.state.scheduler:
        app_.state.scheduler.shutdown(wait=False)


app = FastAPI(title="Training Dashboard", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/auth/whoop/login")
def whoop_login():
    if not config.WHOOP_CLIENT_ID or not config.WHOOP_CLIENT_SECRET:
        raise HTTPException(500, "Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET in .env")
    return RedirectResponse(whoop_auth.build_login_url())


@app.get("/auth/whoop/callback")
def whoop_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(400, f"Whoop authorization failed: {error}")
    if not code or not state or not whoop_auth.consume_state(state):
        raise HTTPException(400, "Invalid or expired state")
    try:
        whoop_auth.exchange_code(code)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Token exchange failed: {exc.response.status_code}")
    return RedirectResponse(config.FRONTEND_URL)


def _last_sync(source: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM sync_log WHERE source=? ORDER BY id DESC LIMIT 1", (source,)
        ).fetchone()
    return dict(row) if row else None


@app.get("/api/status")
def status():
    return {
        "whoop_connected": whoop_auth.is_connected(),
        "last_whoop_sync": _last_sync("whoop"),
        "garmin_connected": config.GARMIN_TOKENS.exists(),
        "last_garmin_sync": _last_sync("garmin"),
        "last_auto_run": _last_sync("scheduled"),
        "next_auto_run": scheduler.next_run(getattr(app.state, "scheduler", None)),
    }


@app.post("/api/sync/garmin")
def sync_garmin_route():
    try:
        return {"synced": sync_garmin()}
    except GarminNotLoggedIn as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/sync/whoop")
def sync_whoop_route():
    try:
        return {"synced": sync_whoop()}
    except NotConnected:
        raise HTTPException(409, "Whoop not connected. Visit /auth/whoop/login")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Whoop API error: {exc.response.status_code}")


def _rows(sql: str, params: tuple = ()):
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


@app.get("/api/recovery")
def recovery(days: int = Query(30, ge=1, le=730)):
    return _rows(
        "SELECT cycle_id, created_at, recovery_score, resting_hr, hrv_rmssd_ms, spo2, skin_temp_c "
        "FROM whoop_recovery WHERE created_at >= datetime('now', ?) ORDER BY created_at",
        (f"-{days} days",),
    )


@app.get("/api/sleep")
def sleep(days: int = Query(30, ge=1, le=730)):
    return _rows(
        "SELECT id, start, end, nap, performance_pct, efficiency_pct, respiratory_rate, light_ms, "
        "sws_ms, rem_ms, awake_ms, in_bed_ms, disturbances FROM whoop_sleep "
        "WHERE start >= datetime('now', ?) ORDER BY start",
        (f"-{days} days",),
    )


@app.get("/api/cycles")
def cycles(days: int = Query(30, ge=1, le=730)):
    return _rows(
        "SELECT id, start, end, strain, avg_hr, max_hr, kilojoule FROM whoop_cycle "
        "WHERE start >= datetime('now', ?) ORDER BY start",
        (f"-{days} days",),
    )


@app.get("/api/whoop/workouts")
def whoop_workouts(days: int = Query(30, ge=1, le=730)):
    return _rows(
        "SELECT id, start, end, sport_name, strain, avg_hr, max_hr, kilojoule, distance_m "
        "FROM whoop_workout WHERE start >= datetime('now', ?) ORDER BY start",
        (f"-{days} days",),
    )


@app.get("/api/activities")
def activities(days: int = Query(90, ge=1, le=730), sport: str | None = None):
    sql = (
        "SELECT id, name, sport, start, distance_m, duration_s, avg_hr, max_hr, avg_speed_ms, "
        "calories, cadence, avg_power, elevation_gain_m, vo2max, aerobic_te, training_load "
        "FROM garmin_activity WHERE start >= datetime('now', ?)"
    )
    params: tuple = (f"-{days} days",)
    if sport:
        sql += " AND sport = ?"
        params += (sport,)
    from .analysis.metrics import normalize_sport

    rows = _rows(sql + " ORDER BY start", params)
    for r in rows:
        r["sport"] = normalize_sport(r["sport"], r["avg_speed_ms"])
    return rows


@app.get("/api/garmin/daily")
def garmin_daily(days: int = Query(90, ge=1, le=730)):
    return _rows(
        "SELECT date, steps, resting_hr, body_battery_high, body_battery_low, avg_stress, vo2max "
        "FROM garmin_daily WHERE date >= date('now', ?) ORDER BY date",
        (f"-{days} days",),
    )


@app.get("/api/insights")
def insights():
    from .analysis.metrics import compute

    acts = _rows(
        "SELECT sport, start, distance_m, duration_s, avg_hr, avg_speed_ms FROM garmin_activity "
        "WHERE start >= datetime('now', '-90 days')"
    )
    rec = _rows(
        "SELECT created_at, recovery_score, resting_hr, hrv_rmssd_ms FROM whoop_recovery "
        "WHERE created_at >= datetime('now', '-60 days')"
    )
    sl = _rows(
        "SELECT end, nap, light_ms, sws_ms, rem_ms FROM whoop_sleep "
        "WHERE end >= datetime('now', '-60 days')"
    )
    return compute(acts, rec, sl)


class ChatRequest(BaseModel):
    message: str


class ProfileUpdate(BaseModel):
    goal: str | None = None
    race_name: str | None = None
    race_date: str | None = None
    max_hr: int | None = None
    gym_days_per_week: int | None = None
    gym_split: str | None = None
    background: str | None = None
    injuries: str | None = None
    notes: str | None = None


@app.get("/api/profile")
def profile_get():
    return profile.get_profile()


@app.put("/api/profile")
def profile_put(update: ProfileUpdate):
    try:
        return profile.save_profile(update.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/coach/goal")
def coach_goal():
    return coach.goal_progress()


@app.get("/api/coach/notes")
def coach_notes():
    return coach.recent_notes(3)


@app.get("/api/coach/summary")
def coach_summary_get():
    return coach.latest_summary() or {"text": None}


@app.post("/api/coach/summary")
def coach_summary_post(force: bool = False):
    try:
        return coach.weekly_summary(force=force)
    except coach.CoachUnavailable as exc:
        raise HTTPException(503, str(exc))


@app.get("/api/coach/chat")
def coach_chat_history():
    return {"messages": coach.chat_history()}


@app.delete("/api/coach/chat")
def coach_chat_clear():
    coach.clear_chat()
    return {"ok": True}


@app.post("/api/coach/chat")
def coach_chat(req: ChatRequest):
    try:
        return {"reply": coach.chat(req.message)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except coach.CoachUnavailable as exc:
        raise HTTPException(503, str(exc))


@app.get("/api/sport-metrics")
def sport_metrics(days: int = Query(365, ge=7, le=730)):
    from .analysis import sport_metrics as sm

    return sm.load(days)


class SetUpdate(BaseModel):
    exercise: str | None = None
    reps: int | None = None
    weight_kg: float | None = None
    duration_s: float | None = None
    deleted: bool | None = None


class SetCreate(BaseModel):
    activity_id: int
    exercise: str
    reps: int
    weight_kg: float


@app.get("/api/lifts")
def lifts_get(days: int = Query(180, ge=7, le=730)):
    return {
        "sessions": lifts.sessions(days),
        "exercises": lifts.exercise_history(365),
        "weekly": lifts.weekly_volume(days),
    }


@app.patch("/api/lifts/sets/{set_id}")
def lifts_update(set_id: int, body: SetUpdate):
    try:
        return lifts.update_set(set_id, body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "Set not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/lifts/sets")
def lifts_add(body: SetCreate):
    try:
        return lifts.add_set(body.activity_id, body.exercise, body.reps, body.weight_kg)
    except KeyError:
        raise HTTPException(404, "Activity not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class CheckBody(BaseModel):
    item: str
    done: bool


@app.get("/api/plan")
def plan_get():
    return plan.get_plan() or {"week_key": plan.current_week_key(), "days": None}


@app.put("/api/plan/check")
def plan_check(body: CheckBody, week_key: str | None = None):
    key = week_key or plan.displayed_week_key() or plan.current_week_key()
    try:
        plan.set_check(key, body.item, body.done)
    except KeyError:
        raise HTTPException(404, "No plan for this week")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return plan.get_plan(key)


@app.post("/api/plan/generate")
def plan_generate():
    """Generate (or regenerate) the plan for the target week, then return the displayed week's plan."""
    try:
        coach.weekly_summary(force=True)
    except coach.CoachUnavailable as exc:
        raise HTTPException(503, str(exc))
    return plan.get_plan() or {"week_key": plan.current_week_key(), "days": None}


@app.get("/api/sleep-schedule")
def sleep_schedule_get(days: int = Query(90, ge=7, le=365)):
    return sleep_schedule.load(days)
