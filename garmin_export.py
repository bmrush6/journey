"""Pull a broad snapshot of a Garmin Connect account into local JSON files.

Reuses the token cache created by garmin_login.py (~/.garminconnect) so it
doesn't need credentials on every run. Fetches account-wide data (profile,
devices, personal records, gear, goals, badges) plus a range of daily
metrics (activities, sleep, steps, heart rate, stress, body battery, HRV,
respiration, SpO2, training readiness/status, weigh-ins) for a given date
range and writes one JSON file per data type into --out.

Usage:
    python3 garmin_export.py --days 7
    python3 garmin_export.py --start 2026-06-01 --end 2026-06-30 --out export/
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_STORE = os.path.expanduser("~/.garminconnect")

# (output filename, method name, args) — args are filled in per date/range below.
ACCOUNT_WIDE = [
    ("profile", "get_user_profile", ()),
    ("devices", "get_devices", ()),
    ("personal_records", "get_personal_record", ()),
    ("goals", "get_goals", ()),
    ("earned_badges", "get_earned_badges", ()),
]


RANGE_METRICS = [
    ("body_battery", "get_body_battery"),
    ("body_composition", "get_body_composition"),
    ("daily_steps", "get_daily_steps"),
    ("race_predictions", "get_race_predictions"),
    ("weigh_ins", "get_weigh_ins"),
]

PER_DAY_METRICS = [
    ("sleep", "get_sleep_data"),
    ("heart_rates", "get_heart_rates"),
    ("resting_heart_rate", "get_rhr_day"),
    ("stress", "get_all_day_stress"),
    ("hydration", "get_hydration_data"),
    ("respiration", "get_respiration_data"),
    ("spo2", "get_spo2_data"),
    ("hrv", "get_hrv_data"),
    ("training_readiness", "get_training_readiness"),
    ("training_status", "get_training_status"),
    ("max_metrics", "get_max_metrics"),
    ("floors", "get_floors"),
    ("intensity_minutes", "get_intensity_minutes_data"),
    ("stats", "get_stats"),
]


def get_profile_id(client: Garmin) -> str | None:
    social_profile = fetch(client, "connectapi", "/userprofile-service/socialProfile")
    if not isinstance(social_profile, dict):
        return None
    for key in ("profileId", "id", "userProfileId"):
        if key in social_profile:
            return str(social_profile[key])
    return None


def save(out_dir: str, name: str, data) -> None:
    path = os.path.join(out_dir, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  wrote {path}")


def fetch(client: Garmin, method_name: str, *args):
    try:
        return getattr(client, method_name)(*args)
    except Exception as exc:
        print(f"  skipped {method_name}: {exc}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Number of days back from today (ignored if --start is set)")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--out", default="garmin_export", help="Output directory")
    parser.add_argument("--activities-limit", type=int, default=50, help="Max recent activities to fetch")
    args = parser.parse_args()

    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=args.days - 1)

    os.makedirs(args.out, exist_ok=True)

    client = Garmin()
    client.login(TOKEN_STORE)
    print(f"Logged in as {client.get_full_name()}")

    print("Account-wide data:")
    for name, method_name, extra_args in ACCOUNT_WIDE:
        save(args.out, name, fetch(client, method_name, *extra_args))

    profile_id = get_profile_id(client)
    if profile_id:
        save(args.out, "gear", fetch(client, "get_gear", profile_id))
    else:
        print("  skipped gear: could not resolve profile id", file=sys.stderr)

    print(f"Activities (up to {args.activities_limit}):")
    save(args.out, "activities", fetch(client, "get_activities", 0, args.activities_limit))

    print(f"Range metrics ({start} to {end}):")
    for name, method_name in RANGE_METRICS:
        save(args.out, name, fetch(client, method_name, start.isoformat(), end.isoformat()))

    print(f"Per-day metrics ({start} to {end}):")
    day_results = {name: {} for name, _ in PER_DAY_METRICS}
    current = start
    while current <= end:
        cdate = current.isoformat()
        for name, method_name in PER_DAY_METRICS:
            day_results[name][cdate] = fetch(client, method_name, cdate)
        current += timedelta(days=1)
    for name, _ in PER_DAY_METRICS:
        save(args.out, name, day_results[name])

    print(f"\nDone. Data written to {os.path.abspath(args.out)}/")


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
