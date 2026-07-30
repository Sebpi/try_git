"""One-time helper: run this locally to mint a Gmail OAuth refresh token.

Usage:
    python scripts/gmail_get_refresh_token.py path/to/client_secret.json

`client_secret.json` is the file Google Cloud Console gives you when you
create an OAuth client ID of type "Desktop app" (APIs & Services ->
Credentials, after enabling the Gmail API on the project). This opens a
browser for the one-time consent screen, then prints the client id/secret/
refresh token to paste into GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET /
GMAIL_REFRESH_TOKEN. The refresh token does not expire on its own -- it's
only invalidated if you revoke access or leave the OAuth consent screen in
"Testing" mode for 7 days without publishing it.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"]


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nSet these environment variables:\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("\n(Optional) GMAIL_SENDER_EMAIL=you@yourdomain.com  "
          "-- only if that's a verified 'Send As' alias on this account.")


if __name__ == "__main__":
    main()
