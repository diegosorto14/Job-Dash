"""
FRP Job Scanner - runs daily, checks for new finance rotational program postings
and emails diego.sorto14@gmail.com with any new findings.

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

# ── Config ────────────────────────────────────────────────────────────────────
EMAIL_TO   = "diego.sorto14@gmail.com"
EMAIL_FROM = "diego.sorto14@gmail.com"   # your Gmail
EMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")  # set as env var

SEEN_FILE  = Path(__file__).parent / "seen_jobs.json"
DATA_FILE  = Path(__file__).parent.parent / "frontend" / "src" / "data" / "new_jobs.json"

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

# ── Load / Save seen jobs ─────────────────────────────────────────────────────
def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(list(seen), indent=2))

# ── Scrapers ──────────────────────────────────────────────────────────────────
def search_indeed(query):
    jobs = []
    try:
        url = f"https://www.indeed.com/jobs?q={requests.utils.quote(query)}&sort=date"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.job_seen_beacon")[:8]
        for card in cards:
            title_el = card.select_one("h2.jobTitle span")
            company_el = card.select_one("span[data-testid='company-name']")
            link_el = card.select_one("a[data-jk]")
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
        print(f"Indeed error: {e}")
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
                uid  = link.split("-")[-1] if link else str(random.randint(10000,99999))
                jobs.append({
                    "title":   title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True),
                    "link":    link,
                    "source":  "LinkedIn",
                    "date":    datetime.date.today().isoformat(),
                    "id":      f"li_{uid}",
                })
    except Exception as e:
        print(f"LinkedIn error: {e}")
    return jobs

def search_handshake(query):
    """
    Handshake requires login for full results.
    We return a direct search URL for the user to click.
    """
    encoded = requests.utils.quote(query)
    return [{
        "title":   f'Search: "{query}"',
        "company": "Multiple — click to view on Handshake",
        "link":    f"https://joinhandshake.com/jobs/?query={encoded}&job_type=JOB",
        "source":  "Handshake",
        "date":    datetime.date.today().isoformat(),
        "id":      f"hs_{encoded[:40]}",
    }]

# ── Main scan ─────────────────────────────────────────────────────────────────
def scan_all():
    seen = load_seen()
    new_jobs = []

    for term in SEARCH_TERMS:
        print(f"Scanning: {term}")
        found = []
        found += search_indeed(term)
        time.sleep(random.uniform(2, 4))
        found += search_linkedin(term)
        time.sleep(random.uniform(2, 4))
        found += search_handshake(term)

        for job in found:
            if job["id"] not in seen:
                seen.add(job["id"])
                new_jobs.append(job)

    save_seen(seen)

    # Write new jobs to frontend data file
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if DATA_FILE.exists():
        existing = json.loads(DATA_FILE.read_text())
    all_jobs = new_jobs + existing
    DATA_FILE.write_text(json.dumps(all_jobs[:200], indent=2))  # keep latest 200

    print(f"Found {len(new_jobs)} new jobs.")
    return new_jobs

# ── Email ─────────────────────────────────────────────────────────────────────
def send_email(new_jobs):
    if not EMAIL_PASS:
        print("⚠ GMAIL_APP_PASSWORD not set — skipping email. Set it in your .env file.")
        return
    if not new_jobs:
        print("No new jobs — no email sent.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 {len(new_jobs)} New FRP Jobs Found — {datetime.date.today()}"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    rows = "".join(f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <strong>{j['title']}</strong><br>
            <span style="color:#666">{j['company']}</span>
          </td>
          <td style="padding:10px;border-bottom:1px solid #eee;color:#888">{j['source']}</td>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <a href="{j['link']}" style="color:#185FA5;text-decoration:none">View →</a>
          </td>
        </tr>
    """ for j in new_jobs)

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto">
      <div style="background:#185FA5;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">🎯 FRP Job Alert</h2>
        <p style="color:#B5D4F4;margin:4px 0 0">{datetime.date.today().strftime('%B %d, %Y')}</p>
      </div>
      <div style="padding:20px;background:#f9f9f9;border-radius:0 0 8px 8px">
        <p>Hey Diego — <strong>{len(new_jobs)} new finance rotational program postings</strong> were found today.</p>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden">
          <thead>
            <tr style="background:#E6F1FB">
              <th style="padding:10px;text-align:left">Role / Company</th>
              <th style="padding:10px;text-align:left">Source</th>
              <th style="padding:10px;text-align:left">Link</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <p style="margin-top:20px;color:#888;font-size:12px">
          Open your dashboard to track applications →
          <a href="http://localhost:3000" style="color:#185FA5">localhost:3000</a>
        </p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"✅ Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"=== FRP Scanner — {datetime.datetime.now()} ===")
    new_jobs = scan_all()
    send_email(new_jobs)
    print("Done.")
