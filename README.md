# journey

## Garmin Connect setup

Install the dependency:

```bash
pip install -r requirements.txt
```

Log in once and cache session tokens to `~/.garminconnect`:

```bash
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=yourpassword python3 garmin_login.py
```

If the variables aren't set, the script prompts for them interactively
(the password prompt is hidden). If two-factor auth is enabled on the
account, you'll be prompted for the MFA code. Subsequent runs reuse the
cached tokens in `~/.garminconnect` and won't need credentials again
until the tokens expire.

Never commit real credentials — use environment variables or a local
`.env` file (already gitignored).

### Exporting your data

Once `garmin_login.py` has cached a session, pull a broad snapshot of the
account into local JSON files:

```bash
python3 garmin_export.py --days 7            # last 7 days, ./garmin_export/
python3 garmin_export.py --start 2026-06-01 --end 2026-06-30 --out export/
```

This writes one JSON file per data type (profile, devices, gear, personal
records, goals, badges, activities, sleep, heart rate, stress, body
battery, HRV, respiration, SpO2, training readiness/status, weigh-ins,
and more) into the output directory. If a particular endpoint isn't
available for your account or device, that one export is skipped with a
warning rather than aborting the whole run.

Exported data is your personal health/fitness data — the output
directory is not committed (add any export folder you use to
`.gitignore` if it isn't already covered).

### Recovery snapshot (what Strava doesn't track)

Strava sees your activities; it doesn't see sleep, HRV, all-day stress,
Body Battery, or resting heart rate. `garmin_recovery.py` pulls just
those five signals for a single date and prints a compact summary:

```bash
python3 garmin_recovery.py --date 2026-06-13
python3 garmin_recovery.py                          # defaults to today
python3 garmin_recovery.py --date 2026-06-13 --out recovery.json
```

The summary fields (sleep score, HRV, stress average, etc.) are a
best-effort read of Garmin's response — if a field name doesn't match
your account/device, that value prints as `None` rather than crashing.
The full raw JSON from each endpoint is always included when writing
with `--out`, so nothing is lost even if a summary field misses.
