"""One-time interactive helper to get a Strava refresh token.

Strava's API requires OAuth. This script prints an authorization link,
waits for you to paste back the page it redirects to after you click
Approve, and exchanges that for a refresh token — no manual curl needed.

Usage:
    python3 strava_login.py --client-id 12345 --client-secret abcdef0123...

(Client ID and secret come from https://www.strava.com/settings/api —
see README.md for how to create an app there.)
"""

import argparse
import sys
from urllib.parse import parse_qs, urlparse

import requests

AUTHORIZE_URL = (
    "https://www.strava.com/oauth/authorize"
    "?client_id={client_id}"
    "&response_type=code"
    "&redirect_uri=http://localhost/exchange_token"
    "&approval_prompt=force"
    "&scope=activity:read_all"
)


def extract_code(pasted: str) -> str:
    pasted = pasted.strip()
    if pasted.startswith("http"):
        code = parse_qs(urlparse(pasted).query).get("code", [None])[0]
        if not code:
            raise ValueError("no 'code' parameter found in that URL")
        return code
    return pasted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    print("1. Open this link in your browser and click Authorize:\n")
    print(f"   {AUTHORIZE_URL.format(client_id=args.client_id)}\n")
    print("2. Your browser will redirect to a 'localhost' page that fails to")
    print("   load — that's expected, nothing is actually running there.")
    print("3. Copy the FULL address from your browser's address bar and paste")
    print("   it below.\n")
    pasted = input("Paste the redirected URL here: ")

    try:
        code = extract_code(pasted)
    except ValueError as exc:
        print(f"Could not find an authorization code in that: {exc}", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    refresh_token = resp.json()["refresh_token"]

    print("\nSuccess! Save these three as GitHub repository secrets:\n")
    print(f"  STRAVA_CLIENT_ID     = {args.client_id}")
    print(f"  STRAVA_CLIENT_SECRET = {args.client_secret}")
    print(f"  STRAVA_REFRESH_TOKEN = {refresh_token}")


if __name__ == "__main__":
    main()
