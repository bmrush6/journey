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

### Nightly job: one database, one row per day per metric — plus fresh recovery JSON

`nightly_job.py` backfills the last 7 days (configurable via
`JOURNEY_DAYS_BACK`) of Garmin recovery metrics and activities into a
SQLite database at `data/journey.db` — one row per day per metric
(`sleep`, `hrv`, `body_battery` tables), one row per activity
(`activities` table, covering runs/rides/etc. — Garmin's devices record
these directly, so there's no need for a separate Strava pull). It's
safe to re-run: rows are upserted by date (or activity id), not
duplicated, so a missed night or a re-run just catches up.

For each day in that window it also calls `garmin_recovery.py`'s
summary function and writes `data/garmin/<date>.json`, then points
`data/garmin/latest.json` at the most recent day that actually returned
data (skipping "today" if Garmin hasn't synced sleep/HRV for it yet).
This is the file downstream tools — like a daily coaching read —
consume, so it's kept current on every run rather than requiring a
manual `garmin_recovery.py --out` call.

```bash
python3 nightly_job.py                  # last 7 days
JOURNEY_DAYS_BACK=14 python3 nightly_job.py
```

To look at the data afterward:
```bash
python3 -c "import sqlite3; c=sqlite3.connect('data/journey.db'); print(c.execute('SELECT * FROM sleep ORDER BY date DESC LIMIT 7').fetchall())"
cat data/garmin/latest.json
```
(or open `data/journey.db` in any SQLite browser).

`.github/workflows/nightly.yml` runs this every morning (~06:00
America/Chicago) on GitHub's runners, which have normal internet access,
and commits the updated database and `data/garmin/*.json` snapshots
back to the repo. It can also be run on demand from the Actions tab
(`workflow_dispatch`).

**One-time setup** (same as `garmin_login.py`, since CI can't do the
interactive MFA prompt):
1. On your own machine: `python3 garmin_login.py`
2. Copy the contents of `~/.garminconnect/garmin_tokens.json`
3. GitHub repo → Settings → Secrets and variables → Actions → New
   repository secret → name `GARMIN_TOKEN_JSON`, value = what you copied

Caveat: this token can expire or get invalidated server-side. If the
nightly workflow starts failing with an authentication error, redo the
steps above and update the secret. There's no fully unattended way
around this with Garmin's unofficial API.

### Ad hoc single-day tools

`garmin_export.py` (broad one-off export, see above) still works
standalone for a one-off deep dive. `garmin_recovery.py` also still
works standalone (e.g. to backfill a date outside the nightly window),
and its summary function is now imported directly by `nightly_job.py`
to build the `data/garmin/*.json` snapshots on every nightly run — so
the two aren't fully independent anymore, `nightly_job.py` is just the
scheduled wrapper around it.
