from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import config
from .db import get_db, init_db
from .garmin.client import GarminNotLoggedIn
from .garmin.sync import sync_garmin
from .whoop import auth as whoop_auth
from .whoop.sync import NotConnected, sync_whoop


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


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
    return _rows(sql + " ORDER BY start", params)


@app.get("/api/garmin/daily")
def garmin_daily(days: int = Query(90, ge=1, le=730)):
    return _rows(
        "SELECT date, steps, resting_hr, body_battery_high, body_battery_low, avg_stress, vo2max "
        "FROM garmin_daily WHERE date >= date('now', ?) ORDER BY date",
        (f"-{days} days",),
    )
