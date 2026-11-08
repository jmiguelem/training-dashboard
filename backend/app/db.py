import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS whoop_token (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_state (
    state TEXT PRIMARY KEY,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS whoop_cycle (
    id INTEGER PRIMARY KEY,
    start TEXT NOT NULL,
    end TEXT,
    strain REAL,
    avg_hr INTEGER,
    max_hr INTEGER,
    kilojoule REAL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS whoop_recovery (
    cycle_id INTEGER PRIMARY KEY,
    sleep_id TEXT,
    created_at TEXT NOT NULL,
    recovery_score REAL,
    resting_hr REAL,
    hrv_rmssd_ms REAL,
    spo2 REAL,
    skin_temp_c REAL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS whoop_sleep (
    id TEXT PRIMARY KEY,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    nap INTEGER NOT NULL,
    performance_pct REAL,
    efficiency_pct REAL,
    respiratory_rate REAL,
    light_ms INTEGER,
    sws_ms INTEGER,
    rem_ms INTEGER,
    awake_ms INTEGER,
    in_bed_ms INTEGER,
    disturbances INTEGER,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS whoop_workout (
    id TEXT PRIMARY KEY,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    sport_name TEXT,
    strain REAL,
    avg_hr INTEGER,
    max_hr INTEGER,
    kilojoule REAL,
    distance_m REAL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS garmin_activity (
    id INTEGER PRIMARY KEY,
    name TEXT,
    sport TEXT,
    start TEXT NOT NULL,
    distance_m REAL,
    duration_s REAL,
    avg_hr REAL,
    max_hr REAL,
    avg_speed_ms REAL,
    calories REAL,
    cadence REAL,
    avg_power REAL,
    elevation_gain_m REAL,
    vo2max REAL,
    aerobic_te REAL,
    training_load REAL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS garmin_daily (
    date TEXT PRIMARY KEY,
    steps INTEGER,
    resting_hr INTEGER,
    body_battery_high INTEGER,
    body_battery_low INTEGER,
    avg_stress INTEGER,
    vo2max REAL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coach_summary (
    week_key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS athlete_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coach_note (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS garmin_laps (
    activity_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    detail TEXT
);
"""


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
