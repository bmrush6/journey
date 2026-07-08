"""Log in to Garmin Connect once and cache session tokens locally.

Credentials are read from the GARMIN_EMAIL / GARMIN_PASSWORD environment
variables so they never need to be hardcoded or committed. Garmin.login()
tries to reuse cached tokens from TOKEN_STORE first; if that fails, it
falls back to email/password (prompting for an MFA code if 2FA is on the
account) and then saves fresh tokens to TOKEN_STORE for next time.
"""

import os
import sys
from getpass import getpass

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_STORE = os.path.expanduser("~/.garminconnect")


def get_credentials() -> tuple[str, str]:
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ")
    password = os.environ.get("GARMIN_PASSWORD") or getpass("Garmin password: ")
    return email, password


def main() -> None:
    email, password = get_credentials()
    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA code: "),
    )
    client.login(TOKEN_STORE)
    print(f"Login successful. Tokens saved to {TOKEN_STORE}")


if __name__ == "__main__":
    try:
        main()
    except GarminConnectAuthenticationError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except (GarminConnectConnectionError, GarminConnectTooManyRequestsError) as exc:
        print(f"Could not reach Garmin Connect: {exc}", file=sys.stderr)
        sys.exit(1)
