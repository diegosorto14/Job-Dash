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
COMPANIES_FILE  = FRONTEND / "companies.json"
STATUS_FILE     = FRONTEND / "app_status.json"
CUSTOM_APPS_FILE = FRONTEND / "custom_apps.json"

# Sector keyword hints for auto-detection
SECTOR_HINTS = {
    "Banking & Financial Services": ["bank","capital","financial","asset management","investment","securities","wealth","insurance","credit","lending"],
    "Tech & Media": ["tech","software","digital","media","cloud","data","ai","intelligence","network","systems"],
    "Healthcare & Pharma": ["health","pharma","medical","biotech","clinical","hospital","care"],
    "Consumer Goods & Retail": ["consumer","retail","brand","foods","beverage","apparel","fashion"],
    "Energy & Utilities": ["energy","oil","gas","power","utility","electric","renewable"],
    "Industrials & Manufacturing": ["industrial","manufacturing","aerospace","defense","engineering","logistics","supply"],
    "Real Estate & REITs": ["real estate","reit","property","realty"],
}

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
        scopes=["https://mail.google.com/"],
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
    """Returns list of company IDs whose name appears in the sender or subject."""
    text = (email["from"] + " " + email["subject"] + " " + email["snippet"]).lower()
    matched = []
    for co in companies:
        name = co["company"].lower()
        short = re.sub(r'\s*(inc\.?|corp\.?|llc\.?|ltd\.?|group|holdings|&\s*co\.?)$', '', name).strip()
        if short and (short in text or name in text):
            matched.append(co["id"])
    return matched

def extract_sender_company(email):
    """Pull company name from the sender's display name or email domain."""
    frm = email["from"]
    # Try display name first: "Goldman Sachs Recruiting <noreply@gs.com>"
    match = re.match(r'^"?([^"<]+)"?\s*<', frm)
    if match:
        name = match.group(1).strip()
        # Strip common recruiting suffixes
        name = re.sub(r'\s*(recruiting|careers|talent|hr|noreply|no-reply|jobs|hiring).*$', '', name, flags=re.I).strip()
        if len(name) > 2:
            return name
    # Fall back to domain: noreply@goldmansachs.com → "goldmansachs"
    domain_match = re.search(r'@([\w-]+)\.(com|org|net|io|co)', frm.lower())
    if domain_match:
        domain = domain_match.group(1).replace('-', ' ').replace('_', ' ')
        return domain.title()
    return None

def guess_sector(text):
    """Guess sector from email content keywords."""
    t = text.lower()
    for sector, hints in SECTOR_HINTS.items():
        if any(h in t for h in hints):
            return sector
    return "Other"

def extract_role_from_subject(subject):
    """Pull a role/program title from the email subject line."""
    # Remove common prefixes like "Thank you for applying to", "Application for"
    cleaned = re.sub(
        r'^(thank you for (applying|your application|your interest)|'
        r'application (received|confirmation|for|submitted)|'
        r'we received your application (for|to)|'
        r'your application to|re:|fw:)\s*',
        '', subject, flags=re.I
    ).strip()
    # Remove trailing "at CompanyName"
    cleaned = re.sub(r'\s+at\s+\S.*$', '', cleaned, flags=re.I).strip()
    return cleaned if len(cleaned) > 3 else subject

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

    custom_apps  = _load_json(CUSTOM_APPS_FILE, [])
    custom_ids   = {a["_id"] for a in custom_apps}
    updates = {}

    for email in emails:
        full_text = email["subject"] + " " + email["body"] + " " + email["snippet"]
        detected_status = classify_email(full_text)
        if not detected_status:
            continue

        matched_ids = match_company(email, companies)

        if matched_ids:
            # ── Known company: update app_status.json ─────────────────────────
            for cid in matched_ids:
                key = str(cid)
                current = app_status.get(key, {}).get("status", "Not Applied")
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

        else:
            # ── Unknown company: auto-create custom application ────────────────
            # Only create if this is an "Applied" confirmation (not interview/offer
            # for a company we simply failed to match)
            if detected_status != "Applied":
                continue

            sender_company = extract_sender_company(email)
            if not sender_company:
                continue

            # Deduplicate: skip if we already have a custom app from this sender
            email_key = "email_" + re.sub(r'[^a-z0-9]', '_', sender_company.lower())[:40]
            if email_key in custom_ids:
                continue

            role   = extract_role_from_subject(email["subject"])
            sector = guess_sector(full_text)

            new_app = {
                "_id":     email_key,
                "company": sender_company,
                "program": role,
                "sector":  sector,
                "url":     "",          # user fills in when they paste the link
                "opens":   "",
                "closes":  "",
                "notes":   f"Auto-added from email: {email['subject'][:80]}",
                "added":   datetime.datetime.now().isoformat(timespec="seconds"),
                "auto":    True,
            }
            # Also set its status
            app_status[email_key] = {
                "status":    "Applied",
                "updated":   datetime.datetime.now().isoformat(timespec="seconds"),
                "email_sub": email["subject"][:100],
            }
            custom_apps.append(new_app)
            custom_ids.add(email_key)
            print(f"  [NEW] Auto-added: {sender_company} — {role}")

    _save_json(STATUS_FILE, app_status)
    _save_json(CUSTOM_APPS_FILE, custom_apps)
    print(f"  Updated {len(updates)} status(es), added {sum(1 for a in custom_apps if a.get('auto'))} auto entries.")
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
