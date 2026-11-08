from datetime import datetime

from app import sleep_schedule as ss
from app.db import get_db
from app.garmin.sync import upsert_sleep


def whoop(i, start_utc, end_utc, offset="-06:00", nap=0):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO whoop_sleep (id, start, end, nap, light_ms, sws_ms, rem_ms, raw) "
            "VALUES (?, ?, ?, ?, 14400000, 3600000, 3600000, ?)",
            (f"w{i}", start_utc, end_utc, nap, f'{{"timezone_offset": "{offset}"}}'),
        )


def test_bed_minutes_wrap_past_midnight():
    assert ss.bed_minutes(datetime(2026, 11, 1, 23, 30)) == 1410
    assert ss.bed_minutes(datetime(2026, 11, 2, 1, 20)) == 1520
    assert ss.clock(1520) == "01:20" and ss.clock(1410) == "23:30"


def test_whoop_times_use_local_offset_and_skip_naps():
    whoop(1, "2026-11-07T07:20:04.440Z", "2026-11-07T13:18:04.750Z")  # 01:20-07:18 local
    whoop(2, "2026-11-07T20:00:00.000Z", "2026-11-07T21:00:00.000Z", nap=1)
    n = ss.whoop_nights(30)
    assert len(n) == 1 and n[0]["bed"] == "01:20" and n[0]["wake"] == "07:18"
    assert n[0]["asleep_h"] == 6.0 and n[0]["date"] == "2026-11-07"


def test_garmin_sleep_stored_in_local_time_and_empty_nights_skipped():
    night = {"dailySleepDTO": {"calendarDate": "2026-11-06", "sleepStartTimestampLocal": 1793920980000,
                               "sleepEndTimestampLocal": 1793955060000, "sleepTimeSeconds": 30000,
                               "deepSleepSeconds": 3000, "lightSleepSeconds": 20000, "remSleepSeconds": 7000,
                               "awakeSleepSeconds": 600, "avgHeartRate": 52.0}, "avgOvernightHrv": 70.0}
    with get_db() as conn:
        assert upsert_sleep(conn, "2026-11-06", night) is True
        assert upsert_sleep(conn, "2026-11-05", {"dailySleepDTO": {"sleepTimeSeconds": 0}}) is False
    g = ss.garmin_nights(365)
    assert len(g) == 1 and g[0]["date"] == "2026-11-06"
    assert g[0]["bed"] == "23:23" and g[0]["wake"] == "08:51"


def test_stats_and_weekend_split():
    nights = []
    for d, bed in [("2026-11-02", "23:00"), ("2026-11-03", "23:00"), ("2026-11-07", "01:00"), ("2026-11-08", "01:00")]:
        h, m = map(int, bed.split(":"))
        b = datetime(2026, 11, 1, h, m)
        w = datetime(2026, 11, 2, 7, 0)
        nights.append(ss._night(d, b, w, 6 * 3600))
    st = ss.stats(nights)
    assert st["weekday_bed"] == "23:00" and st["weekend_bed"] == "01:00" and st["avg_bed"] == "00:00"
    assert st["bed_sd_min"] == 60 and st["nights"] == 4


def test_load_merges_both_sources_by_date_and_summary_is_compact():
    whoop(1, "2026-11-07T07:20:04.440Z", "2026-11-07T13:18:04.750Z")
    d = ss.load(30)
    assert d["nights"][0]["whoop"]["bed"] == "01:20" and d["nights"][0]["garmin"] is None
    assert d["stats"]["garmin"] == {"nights": 0}
    assert ss.coach_summary()["last_10_nights_bed_wake"][0]["whoop"] == "01:20-07:18"
