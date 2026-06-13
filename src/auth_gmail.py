"""
Run once to generate OAuth token files for both Gmail accounts.
Usage:
  python -m src.auth_gmail primary    # matthew.boustead@gmail.com
  python -m src.auth_gmail secondary  # louise.gore.84@gmail.com
"""
import sys
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

CLIENT_SECRET = Path(__file__).parent.parent / "config" / "client_secret.json"
TOKEN_FILES = {
    "primary":   Path(__file__).parent.parent / "config" / "gmail_primary_token.json",
    "secondary": Path(__file__).parent.parent / "config" / "gmail_secondary_token.json",
}
HINTS = {
    "primary":   "matthew.boustead@gmail.com",
    "secondary": "louise.gore.84@gmail.com",
}


def authenticate(account: str):
    token_path = TOKEN_FILES[account]
    hint = HINTS[account]
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        print(f"Token for {account} ({hint}) is already valid.")
        return

    if creds and creds.expired and creds.refresh_token:
        print(f"Refreshing expired token for {account}...")
        creds.refresh(Request())
    else:
        print(f"\nOpening browser for {account} account ({hint}).")
        print("Sign in with that specific Google account when prompted.\n")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0, login_hint=hint)

    token_path.write_text(creds.to_json())
    print(f"Token saved: {token_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("primary", "secondary"):
        print(__doc__)
        sys.exit(1)
    authenticate(sys.argv[1])
