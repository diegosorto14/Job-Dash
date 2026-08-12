"""
Run this ONCE on your local machine to authorize Gmail access.
It will print the three values you need to add as GitHub secrets.

────────────────────────────────────────────────────────────
STEP 1 — Install dependencies (run in terminal):
  pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client

STEP 2 — Get your credentials file:
  1. Go to console.cloud.google.com
  2. Select your "FRP Tracker" project
  3. APIs & Services → Credentials
  4. Click your OAuth 2.0 Client → Download JSON
  5. Rename the downloaded file to: credentials.json
  6. Place it in the same folder as this script

STEP 3 — Run this script:
  python setup_gmail_auth.py
  → A browser window opens → sign in as diego.sorto14@gmail.com → Allow
  → Three values are printed — copy them into GitHub Secrets

STEP 4 — Add to GitHub:
  Go to your repo → Settings → Secrets and variables → Actions
  Update (or create) these three secrets:
    GMAIL_CLIENT_ID
    GMAIL_CLIENT_SECRET
    GMAIL_REFRESH_TOKEN

That's it — the token will never expire again as long as your app
stays in Production mode on Google Cloud Console.
────────────────────────────────────────────────────────────
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# Full Gmail scope — needed to read emails AND send the daily digest
SCOPES = ["https://mail.google.com/"]

def main():
    creds_file = Path(__file__).parent / "credentials.json"
    if not creds_file.exists():
        print("\nERROR: credentials.json not found in this folder.")
        print("Download it from: console.cloud.google.com")
        print("  APIs & Services → Credentials → your OAuth client → Download JSON")
        print("  Rename it to credentials.json and place it here.\n")
        return

    print("\nOpening browser for Gmail authorization...")
    print("Sign in as diego.sorto14@gmail.com and click Allow.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    creds = flow.run_local_server(port=0)

    raw = json.loads(creds_file.read_text())
    # Support both "installed" (Desktop app) and "web" credential types
    client = raw.get("installed") or raw.get("web", {})

    print("\n" + "=" * 60)
    print("  SUCCESS — Add these 3 values as GitHub repository secrets")
    print("=" * 60)
    print(f"\n  GMAIL_CLIENT_ID:\n    {client.get('client_id', '(not found — check credentials.json)')}")
    print(f"\n  GMAIL_CLIENT_SECRET:\n    {client.get('client_secret', '(not found — check credentials.json)')}")
    print(f"\n  GMAIL_REFRESH_TOKEN:\n    {creds.refresh_token}")
    print("\n" + "=" * 60)
    print("\nGo to: github.com/diegosorto14/Job-Dash → Settings → Secrets → Actions")
    print("Update the three secrets above, then the dashboard will auto-update forever.\n")
    print("You can delete credentials.json after saving the secrets — keep it off GitHub!\n")

if __name__ == "__main__":
    main()
