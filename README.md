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

### Nightly job: Garmin + Strava in one database

`nightly_job.py` backfills the last 7 days (configurable via
`JOURNEY_DAYS_BACK`) of Garmin recovery metrics *and* Strava activities
into a single SQLite database at `data/journey.db` — one row per day per
metric (`sleep`, `hrv`, `body_battery` tables), one row per activity
(`runs` table). It's safe to re-run: rows are upserted by date (or
activity id), not duplicated, so a missed night or a re-run just catches
up.

```bash
python3 nightly_job.py                  # last 7 days
JOURNEY_DAYS_BACK=14 python3 nightly_job.py
```

To look at the data afterward:
```bash
python3 -c "import sqlite3; c=sqlite3.connect('data/journey.db'); print(c.execute('SELECT * FROM sleep ORDER BY date DESC LIMIT 7').fetchall())"
```
(or open `data/journey.db` in any SQLite browser).

`.github/workflows/nightly.yml` runs this every morning (~06:00
America/Chicago) on GitHub's runners, which have normal internet access,
and commits the updated database back to the repo. It can also be run on
demand from the Actions tab (`workflow_dispatch`).

**One-time setup — Garmin side** (same as before, since CI can't do the
interactive MFA prompt):
1. On your own machine: `python3 garmin_login.py`
2. Copy the contents of `~/.garminconnect/garmin_tokens.json`
3. GitHub repo → Settings → Secrets and variables → Actions → New
   repository secret → name `GARMIN_TOKEN_JSON`, value = what you copied

**One-time setup — Strava side** (needed for the `runs` table):
1. Go to `strava.com/settings/api` and create an API application (any
   name; for "Authorization Callback Domain" enter `localhost`). This
   gives you a **Client ID** and **Client Secret**.
2. On your own machine, run:
   ```bash
   python3 strava_login.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
   ```
   It prints a link — open it, click **Authorize**, then copy the full
   URL your browser redirects to (it'll look broken/fail to load — that's
   expected) and paste it back into the script. It prints out a refresh
   token.
3. Add three GitHub repository secrets: `STRAVA_CLIENT_ID`,
   `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` (values from steps 1–2).

Caveat: both Garmin's token and Strava's refresh token can expire or get
invalidated server-side (Strava may also rotate the refresh token on
use — this job doesn't write a rotated token back automatically). If the
nightly workflow starts failing with an authentication error, redo the
relevant one-time setup above and update the secret. There's no fully
unattended way around this with an unofficial API (Garmin) or a
long-lived-but-not-permanent token (Strava).

### Ad hoc single-day tools

`garmin_export.py` (broad one-off export, see above) and
`garmin_recovery.py` (quick single-day recovery summary, see above)
still work standalone — they're just no longer on the nightly schedule,
which now runs through `nightly_job.py` instead.
