"""Nightly backfill: last N days of Garmin recovery metrics + Strava
activities into a local SQLite database (data/journey.db) — one row per
day per metric, one row per Strava activity.

Idempotent: re-running the same window upserts rows instead of
duplicating them, so a missed day or a re-run after a fix just catches
up cleanly.

Needs:
- A cached Garmin session at ~/.garminconnect (see garmin_login.py)
- Strava API credentials in the environment: STRAVA_CLIENT_ID,
  STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN (see strava_login.py and
  README.md for the one-time setup)

Usage:
    python3 nightly_job.py                # last 7 days, data/journey.db
    JOURNEY_DAYS_BACK=14 python3 nightly_job.py
"""

import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

import requests
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
CREATE TABLE IF NOT EXISTS runs (
    activity_id TEXT PRIMARY KEY,
    date TEXT,
    name TEXT,
    distance_m REAL,
    moving_time_s INTEGER,
    elapsed_time_s INTEGER,
    avg_speed REAL,
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


def save_run(conn, activity):
    conn.execute(
        "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)",
        (
            str(activity.get("id")),
            (activity.get("start_date_local") or "")[:10],
            activity.get("name"),
            activity.get("distance"),
            activity.get("moving_time"),
            activity.get("elapsed_time"),
            activity.get("average_speed"),
            activity.get("total_elevation_gain"),
        ),
    )


def refresh_strava_token() -> str:
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_strava_activities(access_token: str, after_epoch: int) -> list:
    activities = []
    page = 1
    while True:
        resp = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after_epoch, "per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1
    return activities


def main() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    client = Garmin()
    client.login(TOKEN_STORE)

    days = [date.today() - timedelta(days=i) for i in range(DAYS_BACK)]

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
    after_epoch = int(datetime.combine(oldest, datetime.min.time()).timestamp())
    try:
        access_token = refresh_strava_token()
        activities = fetch_strava_activities(access_token, after_epoch)
        for activity in activities:
            save_run(conn, activity)
        conn.commit()
        print(f"saved {len(activities)} Strava activities since {oldest.isoformat()}")
    except Exception as exc:
        print(f"skipped Strava activities: {exc}", file=sys.stderr)

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
