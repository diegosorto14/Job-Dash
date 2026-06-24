"""
Run this ONCE on your local machine to authorize Gmail access.
It will print three values to add as GitHub secrets.

Steps:
  1. Go to console.cloud.google.com
  2. Create a project → Enable Gmail API
  3. Create OAuth 2.0 credentials (Desktop app) → download as credentials.json
  4. Place credentials.json in the same folder as this script
  5. Run: python setup_gmail_auth.py
  6. A browser window opens → sign in as diego.sorto14@gmail.com → Allow
  7. Copy the three printed values into GitHub Secrets

pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def main():
    creds_file = Path(__file__).parent / "credentials.json"
    if not creds_file.exists():
        print("ERROR: credentials.json not found.")
        print("Download it from console.cloud.google.com → APIs & Services → Credentials")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    creds = flow.run_local_server(port=0)

    client = json.loads(creds_file.read_text())["installed"]

    print("\n" + "="*60)
    print("Add these three values as GitHub repository secrets:")
    print("="*60)
    print(f"\nGMAIL_CLIENT_ID:\n  {client['client_id']}")
    print(f"\nGMAIL_CLIENT_SECRET:\n  {client['client_secret']}")
    print(f"\nGMAIL_REFRESH_TOKEN:\n  {creds.refresh_token}")
    print("\n" + "="*60)
    print("Done! You can delete credentials.json after saving the secrets.")

if __name__ == "__main__":
    main()
