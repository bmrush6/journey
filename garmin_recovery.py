"""Pull the recovery metrics Strava doesn't track for a single day.

Strava's activity feed only sees what happens during a workout. Garmin
Connect also tracks what happens the rest of the time: sleep stages,
overnight HRV, all-day stress, Body Battery (0-100 recovery), and
resting heart rate. This script pulls those five signals for one date
and prints/saves a compact summary.

Reuses the token cache created by garmin_login.py (~/.garminconnect).

Usage:
    python3 garmin_recovery.py --date 2026-06-13
    python3 garmin_recovery.py                      # defaults to today
    python3 garmin_recovery.py --date 2026-06-13 --out recovery.json
"""

import argparse
import json
import os
import sys
from datetime import date

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_STORE = os.path.expanduser("~/.garminconnect")


def dig(value, *path):
    """Best-effort nested lookup that never raises. Field names for these
    endpoints aren't guaranteed across accounts/devices, so any mismatch
    just yields None instead of crashing the summary."""
    try:
        for key in path:
            if value is None:
                return None
            value = value[key] if not isinstance(key, str) else value.get(key)
        return value
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def summarize(d: str, client: Garmin) -> dict:
    sleep = client.get_sleep_data(d)
    hrv = client.get_hrv_data(d)
    stress = client.get_stress_data(d)
    battery = client.get_body_battery(d, d)
    rhr = client.get_rhr_day(d)

    battery_entry = battery[0] if battery else None

    return {
        "date": d,
        "sleep": {
            "score": dig(sleep, "dailySleepDTO", "sleepScores", "overall", "value"),
            "duration_seconds": dig(sleep, "dailySleepDTO", "sleepTimeSeconds"),
            "deep_seconds": dig(sleep, "dailySleepDTO", "deepSleepSeconds"),
            "light_seconds": dig(sleep, "dailySleepDTO", "lightSleepSeconds"),
            "rem_seconds": dig(sleep, "dailySleepDTO", "remSleepSeconds"),
            "awake_seconds": dig(sleep, "dailySleepDTO", "awakeSleepSeconds"),
        },
        "overnight_hrv": dig(hrv, "hrvSummary", "lastNightAvg"),
        "all_day_stress_avg": dig(stress, "avgStressLevel"),
        "body_battery": {
            "charged": dig(battery_entry, "charged"),
            "drained": dig(battery_entry, "drained"),
        },
        "resting_heart_rate": dig(
            rhr, "allMetrics", "metricsMap", "WELLNESS_RESTING_HEART_RATE", 0, "value"
        ),
        "raw": {
            "sleep": sleep,
            "hrv": hrv,
            "stress": stress,
            "body_battery": battery,
            "resting_heart_rate": rhr,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat(), help="Date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--out", help="Optional path to write the full JSON summary")
    args = parser.parse_args()

    client = Garmin()
    client.login(TOKEN_STORE)

    result = summarize(args.date, client)

    print(f"Recovery snapshot for {args.date}")
    print(f"  Sleep score:          {result['sleep']['score']}")
    print(f"  Sleep duration:       {result['sleep']['duration_seconds']} sec")
    print(f"  Overnight HRV:        {result['overnight_hrv']}")
    print(f"  All-day stress (avg): {result['all_day_stress_avg']}")
    print(f"  Body Battery charged: {result['body_battery']['charged']}")
    print(f"  Body Battery drained: {result['body_battery']['drained']}")
    print(f"  Resting heart rate:   {result['resting_heart_rate']}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nFull data written to {args.out}")


if __name__ == "__main__":
    try:
        main()
    except GarminConnectAuthenticationError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        print("Run garmin_login.py first to create a cached session.", file=sys.stderr)
        sys.exit(1)
    except (GarminConnectConnectionError, GarminConnectTooManyRequestsError) as exc:
        print(f"Could not reach Garmin Connect: {exc}", file=sys.stderr)
        sys.exit(1)
