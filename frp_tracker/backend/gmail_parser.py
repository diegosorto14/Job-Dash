"""
Gmail Parser — reads your inbox and auto-updates application statuses.

How it works:
  1. Connects to Gmail via OAuth2 (refresh token stored as GitHub secret)
  2. Fetches emails from the last 3 days
  3. Matches sender/subject against company names in companies.json
  4. Detects rejection, interview, offer, or confirmation keywords
  5. Updates app_status.json which the dashboard reads

Setup (one-time, run locally):
  python setup_gmail_auth.py
  → copy the printed refresh token into GitHub secret GMAIL_REFRESH_TOKEN
"""

import json
import os
import datetime
import re
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BASE       = Path(__file__).parent
FRONTEND   = BASE.parent / "frontend" / "src" / "data"
COMPANIES_FILE = FRONTEND / "companies.json"
STATUS_FILE    = FRONTEND / "app_status.json"

# ── Gmail OAuth config ────────────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("GMAIL_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN", "")

# ── Keyword classification ────────────────────────────────────────────────────
# Each category: if ANY phrase matches the email body/subject → that status
KEYWORDS = {
    "Rejected": [
        "we have decided to move forward with other candidates",
        "we will not be moving forward with your application",
        "not selected for",
        "we regret to inform",
        "unfortunately, we",
        "unfortunately we",
        "after careful consideration, we",
        "we won't be moving forward",
        "we are unable to move forward",
        "we have chosen to move forward with other",
        "position has been filled",
        "we have filled this position",
        "not be pursuing your application",
        "decided to pursue other candidates",
        "not moving forward with your candidacy",
        "we're unable to offer you",
    ],
    "Offer": [
        "pleased to offer you",
        "offer of employment",
        "offer letter",
        "we are excited to offer",
        "congratulations! we would like to offer",
        "welcome to the team",
        "excited to welcome you",
        "we'd like to extend an offer",
    ],
    "Second Round": [
        "final round",
        "second round interview",
        "superday",
        "in-person interview",
        "on-site interview",
        "onsite interview",
        "final interview",
        "we'd like to invite you to our final",
        "advance to the next stage",
        "invited to our assessment center",
    ],
    "First Round": [
        "we'd like to schedule an interview",
        "we would like to invite you to interview",
        "schedule a call",
        "phone screen",
        "phone interview",
        "video interview",
        "hirevue",
        "we are impressed with your background",
        "moving forward with your application",
        "next steps in our process",
        "we'd like to learn more about you",
        "invited to complete an online assessment",
        "complete our online assessment",
        "take our online assessment",
        "we'd like to move forward",
        "advance to the interview",
    ],
    "Applied": [
        "thank you for applying",
        "application received",
        "we received your application",
        "your application has been submitted",
        "successfully submitted your application",
        "application confirmation",
        "thank you for your interest",
        "application for the",
    ],
}

# Status priority: if multiple match, take the highest
STATUS_PRIORITY = ["Offer", "Second Round", "First Round", "Rejected", "Applied"]

# ── Gmail helpers ─────────────────────────────────────────────────────────────
def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)

def fetch_recent_emails(service, days=3):
    after = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
    results = service.users().messages().list(
        userId="me",
        q=f"after:{after}",
        maxResults=200
    ).execute()
    messages = results.get("messages", [])

    emails = []
    for msg in messages:
        m = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
        subject = headers.get("subject", "")
        sender  = headers.get("from", "")
        snippet = m.get("snippet", "")

        # Extract plain text body
        body = _extract_body(m["payload"])

        emails.append({
            "id":      msg["id"],
            "subject": subject,
            "from":    sender,
            "snippet": snippet,
            "body":    body,
        })
    return emails

def _extract_body(payload):
    """Recursively extract plain text from Gmail payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            import base64
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""

# ── Matching ──────────────────────────────────────────────────────────────────
def classify_email(email_text):
    """Return detected status or None."""
    text = email_text.lower()
    for status in STATUS_PRIORITY:
        for phrase in KEYWORDS[status]:
            if phrase in text:
                return status
    return None

def match_company(email, companies):
    """
    Returns list of company IDs whose name appears in the sender or subject.
    """
    text = (email["from"] + " " + email["subject"] + " " + email["snippet"]).lower()
    matched = []
    for co in companies:
        name = co["company"].lower()
        # strip common suffixes for fuzzy matching
        short = re.sub(r'\s*(inc\.?|corp\.?|llc\.?|ltd\.?|group|holdings|&\s*co\.?)$', '', name).strip()
        if short and (short in text or name in text):
            matched.append(co["id"])
    return matched

# ── Main ──────────────────────────────────────────────────────────────────────
def run_parser():
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        print("  Gmail credentials not set — skipping parser.")
        print("  Run setup_gmail_auth.py locally to get credentials.")
        return {}

    print("  Connecting to Gmail...")
    service   = get_gmail_service()
    companies = _load_json(COMPANIES_FILE, [])
    app_status = _load_json(STATUS_FILE, {})

    emails = fetch_recent_emails(service, days=3)
    print(f"  Fetched {len(emails)} recent emails.")

    updates = {}
    for email in emails:
        full_text = email["subject"] + " " + email["body"] + " " + email["snippet"]
        detected_status = classify_email(full_text)
        if not detected_status:
            continue

        matched_ids = match_company(email, companies)
        for cid in matched_ids:
            key = str(cid)
            current = app_status.get(key, {}).get("status", "Not Applied")

            # Only upgrade status, never downgrade (e.g. don't overwrite Offer with Applied)
            current_pri = STATUS_PRIORITY.index(current) if current in STATUS_PRIORITY else 99
            new_pri     = STATUS_PRIORITY.index(detected_status) if detected_status in STATUS_PRIORITY else 99
            if new_pri < current_pri:
                app_status[key] = {
                    "status":    detected_status,
                    "updated":   datetime.datetime.now().isoformat(timespec="seconds"),
                    "email_sub": email["subject"][:100],
                }
                updates[key] = detected_status
                co_name = next((c["company"] for c in companies if c["id"] == cid), key)
                print(f"  [{co_name}] {current} → {detected_status}")

    _save_json(STATUS_FILE, app_status)
    print(f"  Updated {len(updates)} application status(es).")
    return updates

def _load_json(path, default):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return default

def _save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2))

if __name__ == "__main__":
    run_parser()
