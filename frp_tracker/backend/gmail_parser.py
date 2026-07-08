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
        # Additional rejection phrases commonly used
        "we are moving forward with other applicants",
        "we've decided to move forward with other",
        "we decided to move forward with other",
        "your application was not selected",
        "not a fit for this role",
        "not a match for",
        "will not be moving forward",
        "have decided not to move forward",
        "we have chosen not to",
        "no longer considering your application",
        "we won't be proceeding",
        "we are not able to move forward",
        "we're not moving forward",
        "this position has been filled",
        "we have filled the position",
        "the position has been filled",
        "we are pursuing other candidates",
        "we will be pursuing other candidates",
        "we have selected other candidates",
        "not selected to move forward",
        "your background does not meet",
        "your qualifications do not match",
        "we will not be able to offer you",
        "we are not in a position to offer",
        "we cannot offer you a position",
        "we have decided not to proceed",
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
        "we have received your application",
        "your application for",
        "thank you for submitting your application",
    ],
}

# Phrases that MUST appear in subject or body for an unknown company to be
# auto-created. Much stricter than KEYWORDS["Applied"] — no "thank you for
# your interest" type phrases that marketing emails also use.
STRONG_CONFIRMATION_PHRASES = [
    "thank you for applying",
    "application received",
    "we received your application",
    "your application has been submitted",
    "successfully submitted your application",
    "application confirmation",
    "we have received your application",
    "thank you for submitting your application",
]

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
        maxResults=500
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

# Job-related keywords that must appear somewhere in the email for it to count
JOB_KEYWORDS = [
    "application", "apply", "applied", "applicant", "position", "role",
    "interview", "candidate", "recruiting", "recruitment", "hiring",
    "job", "career", "opportunity", "program", "offer", "internship",
    "thank you for your interest", "thank you for applying",
]

# Sender domains/keywords that indicate non-job emails to skip entirely
NON_JOB_SENDERS = [
    "credit", "bank", "card", "alert", "statement", "payment", "invoice",
    "receipt", "order", "shipping", "delivery", "promo", "newsletter",
    "noreply@apple.com", "no-reply@apple.com", "appleid", "icloud",
    "subscri", "unsubscri", "marketing", "notification",
]

# Email relay / bulk-send / transactional infrastructure domains — never a
# real company's confirmation email. Block these from auto-creating entries.
RELAY_DOMAINS = {
    "emailrelay.io", "sendgrid.net", "mailchimp.com", "mandrillapp.com",
    "mailgun.org", "amazonses.com", "sparkpostmail.com", "postmarkapp.com",
    "mcsv.net", "list-manage.com", "constantcontact.com", "exacttarget.com",
    "salesforce.com", "marketo.com", "hubspot.com", "intercom.io",
    "reply.io", "outreach.io", "salesloft.com",
}

# Free/personal email providers — a real company never sends from these
FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "aol.com", "protonmail.com",
}

REJECT_SUBJECTS = [
    "complete your", "finish your application", "don't forget to apply",
    "you left something behind", "your application is incomplete",
    "reminder: your application", "action required:", "action needed:",
    "emailrelay", "unsubscribe", "verify your email", "confirm your email",
    "please verify", "account verification",
    # ATS "welcome to portal" emails — account creation, not application confirmation
    "applicant hub", "applicant portal", "candidate portal", "career portal",
    "welcome to your account", "your account has been created",
]

# Applicant Tracking System platform names — when the sender display name IS one
# of these, the real employer is someone else; auto-creating "Workday" as a
# company would be a false positive.
ATS_PLATFORMS = {
    "workday", "greenhouse", "lever", "taleo", "icims", "jobvite",
    "bamboohr", "successfactors", "oracle hcm", "oracle", "servicenow",
    "service now", "smartrecruiters", "jazz hr", "jazzhr", "breezy hr",
    "recruitee", "ashby", "rippling", "adp", "paylocity", "paychex",
    "myworkdayjobs", "ultipro", "ukg", "kronos", "cornerstone",
}

def is_job_email(email):
    """Return True only if the email looks like a genuine job-related message."""
    sender = email["from"].lower()
    subject = email["subject"].lower()
    body = (email.get("body", "") + " " + email.get("snippet", "")).lower()
    full = sender + " " + subject + " " + body

    # Skip if sender looks non-job
    if any(kw in sender for kw in NON_JOB_SENDERS):
        return False

    # Skip relay/bulk-mail infrastructure domains
    domain_match = re.search(r'@([\w.-]+)', sender)
    sender_domain = domain_match.group(1) if domain_match else ""
    if sender_domain in RELAY_DOMAINS:
        return False
    # Also check any subdomain (e.g. em.emailrelay.io)
    if any(sender_domain.endswith("." + d) for d in RELAY_DOMAINS):
        return False

    # Skip incomplete-application reminders and generic marketing
    if any(phrase in subject for phrase in REJECT_SUBJECTS):
        return False

    # Must contain at least one explicit job keyword in subject or body
    # (NOT just "thank you for your interest" which is in every marketing email)
    JOB_SUBJECT_KEYWORDS = [
        "application", "apply", "applied", "applicant", "position", "role",
        "interview", "candidate", "recruiting", "recruitment", "hiring",
        "job", "career", "program", "offer", "internship",
        "thank you for applying", "we received your application",
    ]
    return any(kw in full for kw in JOB_SUBJECT_KEYWORDS)

def classify_email(email_text):
    """Return detected status or None."""
    text = email_text.lower()
    for status in STATUS_PRIORITY:
        for phrase in KEYWORDS[status]:
            if phrase in text:
                return status
    return None

def _company_patterns(co):
    """Pre-compute match patterns for a company dict. Returns (short, patterns_list)."""
    name = co["company"].lower()
    short = re.sub(
        r'\s*(inc\.?|corp\.?|llc\.?|ltd\.?|group|holdings|&\s*co\.?|'
        r'laboratories|lab|solutions|technologies|systems|services|financial|capital)$',
        '', name
    ).strip()
    first_word = short.split()[0] if short.split() else ""

    if len(short) < 4:
        return short, []

    pats = [re.compile(r'\b' + re.escape(short) + r'\b'),
            re.compile(r'\b' + re.escape(name) + r'\b')]
    if len(first_word) >= 5:
        pats.append(re.compile(r'\b' + re.escape(first_word) + r'\b'))
    # Domain pattern: "ge vernova" → "gevernova"
    pats.append(re.compile(re.escape(short.replace(' ', ''))))
    return short, pats


def _any_match(pats, text):
    return any(p.search(text) for p in pats)


def match_company(email, companies):
    """
    Match an email to a company in the list using 4 priority levels:
      L1 — sender email domain  (most reliable)
      L2 — sender display name
      L3 — email subject        (requires strong confirmation phrase in body)
      L4 — email body text      (requires strong confirmation phrase)  ← catches ATS senders
    Returns a list with exactly one company ID, or [] if no confident match.
    """
    sender  = email["from"].lower()
    subject = email["subject"].lower()
    body    = (email.get("body", "") + " " + email.get("snippet", "")).lower()

    domain_m      = re.search(r'@([\w.-]+)', sender)
    sender_domain = domain_m.group(1) if domain_m else ""
    sender_name   = re.sub(r'<.*?>', '', sender).strip().strip('"')

    # A strong confirmation phrase must be present for L3/L4 to fire —
    # prevents a company name buried in a newsletter body from flipping status.
    confirmed = any(p in body or p in subject for p in STRONG_CONFIRMATION_PHRASES)

    domain_hits, name_hits, subject_hits, body_hits = [], [], [], []

    for co in companies:
        short, pats = _company_patterns(co)
        if not pats:
            continue

        # L1: company name appears in the sender's email domain
        if any(p.search(sender_domain) for p in pats):
            domain_hits.append(co["id"])
            continue

        # L2: company name appears in sender display name
        if _any_match(pats, sender_name):
            name_hits.append(co["id"])
            continue

        # L3: company name in subject (only when email is a confirmed application)
        if confirmed and _any_match(pats, subject):
            subject_hits.append(co["id"])
            continue

        # L4: company name anywhere in the email body
        # This catches ATS-sent emails (Workday, iCIMS, Taleo, etc.) where the
        # sender domain is the ATS platform, not the employer — the body almost
        # always says "thank you for applying to <Company>" explicitly.
        if confirmed and _any_match(pats, body):
            body_hits.append(co["id"])

    # Return exactly one match from the highest-confidence level.
    # If multiple companies match at the same level it's ambiguous — skip.
    for level, hits, label in [
        (0, domain_hits,  "domain"),
        (1, name_hits,    "display name"),
        (2, subject_hits, "subject"),
        (3, body_hits,    "body"),
    ]:
        if len(hits) == 1:
            if level >= 2:
                co_name = next((c["company"] for c in companies if c["id"] == hits[0]), hits[0])
                print(f"  [L{level+1} {label} match] {co_name} ← {email['subject'][:60]}")
            return hits
        if len(hits) > 1:
            names = [next((c["company"] for c in companies if c["id"] == h), h) for h in hits]
            print(f"  [Ambiguous L{level+1}] {names} — skipping: {email['subject'][:60]}")
            return []

    return []

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

def extract_interview_details(email):
    """Extract date, time, format, and a plain-English summary from an interview email."""
    body    = email.get("body", "")
    subject = email.get("subject", "")
    full    = subject + " " + body

    # ── Date extraction ──────────────────────────────────────────────────────
    date_str = None
    date_patterns = [
        r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})\b',
        r'\b((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s+'
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)\b',
        r'\b(\d{1,2}/\d{1,2}/\d{4})\b',
        r'\b(\d{4}-\d{2}-\d{2})\b',
    ]
    for pat in date_patterns:
        m = re.search(pat, full, re.I)
        if m:
            date_str = m.group(1).strip()
            break

    # ── Time extraction ──────────────────────────────────────────────────────
    time_str = None
    time_m = re.search(r'\b(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)(?:\s*[A-Z]{1,3}T)?)\b', full)
    if time_m:
        time_str = time_m.group(1).strip()

    # ── Format detection ─────────────────────────────────────────────────────
    t = full.lower()
    if "hirevue" in t:
        fmt = "HireVue (Recorded Video)"
    elif "in-person" in t or "onsite" in t or "on-site" in t:
        fmt = "In-Person"
    elif "zoom" in t or "microsoft teams" in t or "google meet" in t or "webex" in t or "video interview" in t or "video call" in t:
        fmt = "Video Call"
    elif "phone screen" in t or "phone interview" in t or "phone call" in t:
        fmt = "Phone Screen"
    elif "online assessment" in t or "assessment center" in t or "pymetrics" in t or "codility" in t:
        fmt = "Online Assessment"
    elif "superday" in t or "final round" in t:
        fmt = "Superday / Final Round"
    else:
        fmt = "Interview"

    # ── Summary: pull meaningful sentences from the body ─────────────────────
    summary = ""
    if body:
        cleaned = re.sub(r'^(dear\s+[\w\s,]+[.]\s*)', '', body.strip(), flags=re.I)
        cleaned = re.sub(
            r'(best regards?|sincerely|thank you,?|regards?,?|warm regards?|'
            r'unsubscribe|privacy policy|this email was sent)[\s\S]*$',
            '', cleaned, flags=re.I
        ).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned)
        summary = cleaned[:450].strip()
        if len(cleaned) > 450:
            summary += "…"

    return {
        "date":    date_str,
        "time":    time_str,
        "format":  fmt,
        "summary": summary,
    }


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

    emails = fetch_recent_emails(service, days=21)
    print(f"  Fetched {len(emails)} recent emails (21-day window).")

    custom_apps  = _load_json(CUSTOM_APPS_FILE, [])
    custom_ids   = {a["_id"] for a in custom_apps}
    updates = {}

    for email in emails:
        # Skip non-job emails entirely before any further processing
        if not is_job_email(email):
            continue

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
                    entry = {
                        "status":    detected_status,
                        "updated":   datetime.datetime.now().isoformat(timespec="seconds"),
                        "email_sub": email["subject"][:100],
                    }
                    # Extract interview details for any round advancement
                    if detected_status in ("First Round", "Second Round", "Offer"):
                        details = extract_interview_details(email)
                        entry["interview"] = details
                        co_name_log = next((c["company"] for c in companies if c["id"] == cid), key)
                        print(f"  [{co_name_log}] Interview details extracted — {details['format']}"
                              + (f" on {details['date']}" if details['date'] else ""))
                    app_status[key] = entry
                    updates[key] = detected_status
                    co_name = next((c["company"] for c in companies if c["id"] == cid), key)
                    print(f"  [{co_name}] {current} → {detected_status}")

        else:
            # ── Unknown company: auto-create custom application ────────────────
            # Requirements before creating:
            #   1. Status must be "Applied" (never auto-create from interview/offer
            #      emails for companies we didn't match — we might have matched wrong)
            #   2. Subject/body must contain a STRONG confirmation phrase
            #      (not just "thank you for your interest" which is in newsletters)
            #   3. Sender must NOT be a relay service or free email provider
            if detected_status != "Applied":
                continue

            # Gate 1: strong confirmation phrase required
            strong_hit = any(p in full_text.lower() or p in email["subject"].lower()
                             for p in STRONG_CONFIRMATION_PHRASES)
            if not strong_hit:
                print(f"  [SKIP auto-create] No strong confirmation phrase: {email['subject'][:60]}")
                continue

            # Gate 2: sender must be a real company domain
            domain_match_auto = re.search(r'@([\w.-]+)', email["from"].lower())
            sender_domain_auto = domain_match_auto.group(1) if domain_match_auto else ""
            if (sender_domain_auto in RELAY_DOMAINS or
                    any(sender_domain_auto.endswith("." + d) for d in RELAY_DOMAINS) or
                    sender_domain_auto in FREEMAIL_DOMAINS):
                print(f"  [SKIP auto-create] Relay/freemail sender ({sender_domain_auto}): {email['subject'][:60]}")
                continue

            sender_company = extract_sender_company(email)
            if not sender_company:
                continue

            # Gate 3: sender display name must not be an ATS platform
            if sender_company.lower().strip() in ATS_PLATFORMS:
                print(f"  [SKIP auto-create] ATS platform sender ({sender_company}): {email['subject'][:60]}")
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
                "url":     "",
                "opens":   "",
                "closes":  "",
                "notes":   f"Auto-added from email: {email['subject'][:80]}",
                "added":   datetime.datetime.now().isoformat(timespec="seconds"),
                "auto":    True,
            }
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
