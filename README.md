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

### Automated daily pull

`.github/workflows/garmin-daily.yml` runs `garmin_recovery.py` every
morning (~06:00 America/Chicago) on GitHub's runners — which have
normal internet access — and commits the result to
`data/garmin/<date>.json` and `data/garmin/latest.json`. GitHub only
fires scheduled workflows from the default branch, so this starts
running once merged there. It can also be run on demand from the
Actions tab (`workflow_dispatch`).

One-time setup, since Garmin's login flow needs an interactive MFA
prompt that CI can't do:

1. On your own machine: `python3 garmin_login.py` (enter your MFA code
   if asked). This creates `~/.garminconnect/garmin_tokens.json`.
2. Copy that file's contents.
3. In the GitHub repo: Settings → Secrets and variables → Actions → New
   repository secret, name `GARMIN_TOKEN_JSON`, value = the file
   contents you copied.

Caveat: this token can expire or be invalidated server-side. If the
workflow starts failing with an authentication error, redo steps 1–3
to refresh the secret. There's no fully unattended way around this
with Garmin's unofficial API.
