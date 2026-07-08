"""Nightly backfill: last N days of Garmin recovery metrics and
activities into a local SQLite database (data/journey.db) — one row per
day per metric, one row per activity. Garmin devices record activities
directly, so this covers what Strava would show plus the recovery
metrics (sleep, HRV, Body Battery) Strava doesn't track, all from one
source.

Idempotent: re-running the same window upserts rows instead of
duplicating them, so a missed day or a re-run after a fix just catches
up cleanly.

Needs a cached Garmin session at ~/.garminconnect (see garmin_login.py).

Usage:
    python3 nightly_job.py                # last 7 days, data/journey.db
    JOURNEY_DAYS_BACK=14 python3 nightly_job.py
"""

import os
import sqlite3
import sys
from datetime import date, timedelta

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_STORE = os.path.expanduser("~/.garminconnect")
DB_PATH = os.environ.get("JOURNEY_DB_PATH", "data/journey.db")
DAYS_BACK = int(os.environ.get("JOURNEY_DAYS_BACK", "7"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sleep (
    date TEXT PRIMARY KEY,
    score INTEGER,
    duration_seconds INTEGER,
    deep_seconds INTEGER,
    light_seconds INTEGER,
    rem_seconds INTEGER,
    awake_seconds INTEGER
);
CREATE TABLE IF NOT EXISTS hrv (
    date TEXT PRIMARY KEY,
    overnight_avg INTEGER
);
CREATE TABLE IF NOT EXISTS body_battery (
    date TEXT PRIMARY KEY,
    charged INTEGER,
    drained INTEGER
);
CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    date TEXT,
    name TEXT,
    type TEXT,
    distance_m REAL,
    duration_s REAL,
    avg_speed_mps REAL,
    calories REAL,
    elevation_gain_m REAL
);
"""


def dig(value, *path):
    """Best-effort nested lookup that never raises (see garmin_recovery.py)."""
    try:
        for key in path:
            if value is None:
                return None
            value = value[key] if not isinstance(key, str) else value.get(key)
        return value
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def save_sleep(conn, d, sleep):
    dto = (sleep or {}).get("dailySleepDTO") or {}
    conn.execute(
        "INSERT OR REPLACE INTO sleep VALUES (?,?,?,?,?,?,?)",
        (
            d,
            dig(dto, "sleepScores", "overall", "value"),
            dto.get("sleepTimeSeconds"),
            dto.get("deepSleepSeconds"),
            dto.get("lightSleepSeconds"),
            dto.get("remSleepSeconds"),
            dto.get("awakeSleepSeconds"),
        ),
    )


def save_hrv(conn, d, hrv):
    conn.execute(
        "INSERT OR REPLACE INTO hrv VALUES (?,?)",
        (d, dig(hrv, "hrvSummary", "lastNightAvg")),
    )


def save_body_battery(conn, d, battery):
    entry = battery[0] if battery else None
    conn.execute(
        "INSERT OR REPLACE INTO body_battery VALUES (?,?,?)",
        (d, dig(entry, "charged"), dig(entry, "drained")),
    )


def save_activity(conn, activity):
    conn.execute(
        "INSERT OR REPLACE INTO activities VALUES (?,?,?,?,?,?,?,?,?)",
        (
            str(activity.get("activityId")),
            (activity.get("startTimeLocal") or "")[:10],
            activity.get("activityName"),
            dig(activity, "activityType", "typeKey"),
            activity.get("distance"),
            activity.get("duration"),
            activity.get("averageSpeed"),
            activity.get("calories"),
            activity.get("elevationGain"),
        ),
    )


def main() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    client = Garmin()
    client.login(TOKEN_STORE)

    today = date.today()
    days = [today - timedelta(days=i) for i in range(DAYS_BACK)]

    for d in days:
        cdate = d.isoformat()
        try:
            save_sleep(conn, cdate, client.get_sleep_data(cdate))
        except Exception as exc:
            print(f"skipped sleep {cdate}: {exc}", file=sys.stderr)
        try:
            save_hrv(conn, cdate, client.get_hrv_data(cdate))
        except Exception as exc:
            print(f"skipped hrv {cdate}: {exc}", file=sys.stderr)
        try:
            save_body_battery(conn, cdate, client.get_body_battery(cdate, cdate))
        except Exception as exc:
            print(f"skipped body_battery {cdate}: {exc}", file=sys.stderr)
        conn.commit()
        print(f"saved Garmin metrics for {cdate}")

    oldest = days[-1]
    try:
        activities = client.get_activities_by_date(oldest.isoformat(), today.isoformat())
        for activity in activities:
            save_activity(conn, activity)
        conn.commit()
        print(f"saved {len(activities)} activities since {oldest.isoformat()}")
    except Exception as exc:
        print(f"skipped activities: {exc}", file=sys.stderr)

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except GarminConnectAuthenticationError as exc:
        print(f"Garmin authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except (GarminConnectConnectionError, GarminConnectTooManyRequestsError) as exc:
        print(f"Could not reach Garmin Connect: {exc}", file=sys.stderr)
        sys.exit(1)
