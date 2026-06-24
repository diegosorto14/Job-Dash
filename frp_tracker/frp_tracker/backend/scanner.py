"""
FRP Job Scanner — runs daily, checks for new finance rotational program postings,
detects programs not in the original 100, and emails diego.sorto14@gmail.com.

Run manually:    python scanner.py
Schedule daily:  add to cron (see README)
"""

import json
import os
import smtplib
import datetime
import time
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
EMAIL_TO   = "diego.sorto14@gmail.com"
EMAIL_FROM = "diego.sorto14@gmail.com"
EMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")

FRONTEND_DATA = Path(__file__).parent.parent / "frontend" / "src" / "data"
SEEN_FILE        = Path(__file__).parent / "seen_jobs.json"
NEW_JOBS_FILE    = FRONTEND_DATA / "new_jobs.json"
NEW_PROGRAMS_FILE= FRONTEND_DATA / "new_programs.json"
ACTIVITY_LOG     = FRONTEND_DATA / "activity_log.json"
COMPANIES_FILE   = FRONTEND_DATA / "companies.json"

SEARCH_TERMS = [
    "finance rotational program 2027",
    "FP&A rotational program new grad 2027",
    "finance leadership development program 2027",
    "finance rotation program analyst 2027",
    "financial planning analysis rotational 2027",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text())
    except Exception:
        pass
    return default

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2))

def known_companies():
    """Return set of lowercase company names already in the original 100."""
    companies = load_json(COMPANIES_FILE, [])
    return {c["company"].lower() for c in companies}

# ── Scrapers ──────────────────────────────────────────────────────────────────
def search_indeed(query):
    jobs = []
    try:
        url = f"https://www.indeed.com/jobs?q={requests.utils.quote(query)}&sort=date"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.job_seen_beacon")[:8]
        for card in cards:
            title_el   = card.select_one("h2.jobTitle span")
            company_el = card.select_one("span[data-testid='company-name']")
            link_el    = card.select_one("a[data-jk]")
            if title_el and company_el and link_el:
                jk = link_el.get("data-jk", "")
                jobs.append({
                    "title":   title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True),
                    "link":    f"https://www.indeed.com/viewjob?jk={jk}",
                    "source":  "Indeed",
                    "date":    datetime.date.today().isoformat(),
                    "id":      f"indeed_{jk}",
                })
    except Exception as e:
        print(f"  Indeed error: {e}")
    return jobs

def search_linkedin(query):
    jobs = []
    try:
        url = (
            f"https://www.linkedin.com/jobs/search/?keywords={requests.utils.quote(query)}"
            f"&sortBy=DD&f_TPR=r86400"
        )
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.base-card")[:8]
        for card in cards:
            title_el   = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            link_el    = card.select_one("a.base-card__full-link")
            if title_el and company_el and link_el:
                link = link_el.get("href", "").split("?")[0]
                uid  = link.split("-")[-1] if link else str(random.randint(10000, 99999))
                jobs.append({
                    "title":   title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True),
                    "link":    link,
                    "source":  "LinkedIn",
                    "date":    datetime.date.today().isoformat(),
                    "id":      f"li_{uid}",
                })
    except Exception as e:
        print(f"  LinkedIn error: {e}")
    return jobs

def search_handshake(query):
    encoded = requests.utils.quote(query)
    return [{
        "title":   f'Search: "{query}"',
        "company": "Multiple — click to view on Handshake",
        "link":    f"https://joinhandshake.com/jobs/?query={encoded}&job_type=JOB",
        "source":  "Handshake",
        "date":    datetime.date.today().isoformat(),
        "id":      f"hs_{encoded[:40]}",
    }]

# ── Classify new vs known programs ────────────────────────────────────────────
def classify_jobs(jobs):
    """Split jobs into known-company jobs and potentially new programs."""
    known = known_companies()
    known_jobs, new_programs = [], []
    for job in jobs:
        co = job.get("company", "").lower()
        # Handshake catch-all links aren't real new programs
        if "multiple" in co or "handshake" in co:
            known_jobs.append(job)
            continue
        if any(k in co or co in k for k in known):
            known_jobs.append(job)
        else:
            new_programs.append(job)
    return known_jobs, new_programs

# ── Main scan ─────────────────────────────────────────────────────────────────
def scan_all():
    seen = set(load_json(SEEN_FILE, []))
    new_jobs, discovered_programs = [], []
    errors = []

    for term in SEARCH_TERMS:
        print(f"  Scanning: {term}")
        found = []
        try:
            found += search_indeed(term)
            time.sleep(random.uniform(2, 4))
            found += search_linkedin(term)
            time.sleep(random.uniform(2, 4))
            found += search_handshake(term)
        except Exception as e:
            errors.append(str(e))

        for job in found:
            if job["id"] not in seen:
                seen.add(job["id"])
                new_jobs.append(job)

    save_json(SEEN_FILE, list(seen))

    # Classify new vs known
    known_jobs, new_progs = classify_jobs(new_jobs)

    # Save new jobs feed
    existing_jobs = load_json(NEW_JOBS_FILE, [])
    save_json(NEW_JOBS_FILE, (known_jobs + existing_jobs)[:200])

    # Save newly discovered programs (not in original 100)
    existing_progs = load_json(NEW_PROGRAMS_FILE, [])
    existing_ids   = {p["id"] for p in existing_progs}
    fresh_progs    = [p for p in new_progs if p["id"] not in existing_ids]
    save_json(NEW_PROGRAMS_FILE, (fresh_progs + existing_progs)[:500])

    print(f"  Found {len(known_jobs)} new job postings, {len(fresh_progs)} new programs.")
    return known_jobs, fresh_progs, errors

# ── Activity log ──────────────────────────────────────────────────────────────
def log_activity(new_jobs, new_programs, email_sent, email_error=None, errors=None):
    log = load_json(ACTIVITY_LOG, [])
    entry = {
        "ts":           datetime.datetime.now().isoformat(timespec="seconds"),
        "date":         datetime.date.today().isoformat(),
        "new_jobs":     len(new_jobs),
        "new_programs": len(new_programs),
        "email_sent":   email_sent,
        "email_error":  email_error,
        "scan_errors":  errors or [],
    }
    log.insert(0, entry)
    save_json(ACTIVITY_LOG, log[:90])  # keep ~3 months
    return entry

# ── Email ─────────────────────────────────────────────────────────────────────
def send_email(new_jobs, new_programs):
    if not EMAIL_PASS:
        print("  ⚠ GMAIL_APP_PASSWORD not set — skipping email.")
        return False, "GMAIL_APP_PASSWORD not set"
    if not new_jobs and not new_programs:
        print("  No new findings — no email sent.")
        return False, None

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 FRP Scanner — {len(new_jobs)} jobs, {len(new_programs)} new programs ({datetime.date.today()})"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    def job_rows(jobs):
        return "".join(f"""
            <tr>
              <td style="padding:10px;border-bottom:1px solid #eee">
                <strong>{j['title']}</strong><br>
                <span style="color:#666">{j['company']}</span>
              </td>
              <td style="padding:10px;border-bottom:1px solid #eee;color:#888">{j['source']}</td>
              <td style="padding:10px;border-bottom:1px solid #eee">
                <a href="{j['link']}" style="color:#1d4ed8">View →</a>
              </td>
            </tr>
        """ for j in jobs)

    jobs_section = ""
    if new_jobs:
        jobs_section = f"""
        <h3 style="margin:20px 0 10px;color:#1e293b">📋 New Job Postings ({len(new_jobs)})</h3>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px">
          <thead><tr style="background:#eff6ff">
            <th style="padding:10px;text-align:left">Role / Company</th>
            <th style="padding:10px;text-align:left">Source</th>
            <th style="padding:10px;text-align:left">Link</th>
          </tr></thead>
          <tbody>{job_rows(new_jobs)}</tbody>
        </table>"""

    progs_section = ""
    if new_programs:
        progs_section = f"""
        <h3 style="margin:20px 0 10px;color:#1e293b">🔭 New Programs Discovered ({len(new_programs)})</h3>
        <p style="font-size:13px;color:#64748b;margin-bottom:8px">These companies are not in your original 100 — worth checking out!</p>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px">
          <thead><tr style="background:#f0fdf4">
            <th style="padding:10px;text-align:left">Role / Company</th>
            <th style="padding:10px;text-align:left">Source</th>
            <th style="padding:10px;text-align:left">Link</th>
          </tr></thead>
          <tbody>{job_rows(new_programs)}</tbody>
        </table>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto">
      <div style="background:#0f172a;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">🎯 FRP Daily Scan</h2>
        <p style="color:#94a3b8;margin:4px 0 0">{datetime.date.today().strftime('%B %d, %Y')}</p>
      </div>
      <div style="padding:20px;background:#f8fafc;border-radius:0 0 8px 8px">
        <p>Hey Diego — here's what the scanner found today.</p>
        {jobs_section}
        {progs_section}
        <p style="margin-top:24px;color:#94a3b8;font-size:12px">
          Open your dashboard → <a href="http://localhost:3000" style="color:#1d4ed8">localhost:3000</a>
        </p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"  ✅ Email sent to {EMAIL_TO}")
        return True, None
    except Exception as e:
        print(f"  ❌ Email failed: {e}")
        return False, str(e)

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"=== FRP Scanner — {datetime.datetime.now()} ===")
    new_jobs, new_programs, scan_errors = scan_all()
    email_sent, email_error = send_email(new_jobs, new_programs)
    entry = log_activity(new_jobs, new_programs, email_sent, email_error, scan_errors)
    print(f"Done. Logged to activity_log.json")
