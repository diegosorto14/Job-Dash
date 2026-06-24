"""
FRP Job Scanner — runs daily via GitHub Actions.
  - Scans Indeed / LinkedIn / Handshake for new FRP postings
  - Sends deadline alerts (7-day warning) for programs closing soon
  - Emails a daily digest and, on Sundays, a weekly summary
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

BASE         = Path(__file__).parent
FRONTEND     = BASE.parent / "frontend" / "src" / "data"
SEEN_FILE         = BASE / "seen_jobs.json"
NEW_JOBS_FILE     = FRONTEND / "new_jobs.json"
NEW_PROGRAMS_FILE = FRONTEND / "new_programs.json"
ACTIVITY_LOG      = FRONTEND / "activity_log.json"
COMPANIES_FILE    = FRONTEND / "companies.json"
STATUS_FILE       = FRONTEND / "app_status.json"   # written by gmail_parser

MONTH_TO_NUM = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12
}

SEARCH_TERMS = [
    '"finance rotational program" 2027',
    '"finance leadership development program" 2027',
    '"finance rotation program" analyst 2027',
    '"financial rotational program" new grad 2027',
    '"finance development program" 2027',
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
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return default

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2))

ROTATIONAL_KEYWORDS = [
    "rotational", "rotation program", "leadership development",
    "development program", "ldp", "fdp", "fldp", "frap", "afrp",
    "finance program", "finance associate program",
    "finance & strategy", "finance and strategy",
    "new grad", "new analyst", "analyst program",
]

def is_rotational(title):
    """Return True only if the job title looks like a rotational/dev program."""
    t = title.lower()
    return any(kw in t for kw in ROTATIONAL_KEYWORDS)

def known_companies():
    companies = load_json(COMPANIES_FILE, [])
    return {c["company"].lower() for c in companies}

def already_applied_companies():
    """Return lowercase company names where status is Applied or further."""
    app_status = load_json(STATUS_FILE, {})
    companies  = load_json(COMPANIES_FILE, [])
    applied_statuses = {"Applied", "First Round", "Second Round", "Offer", "Rejected"}
    applied_ids = {cid for cid, v in app_status.items()
                   if v.get("status") in applied_statuses}
    return {c["company"].lower() for c in companies if str(c["id"]) in applied_ids}

# ── Scrapers ──────────────────────────────────────────────────────────────────
def search_indeed(query):
    jobs = []
    try:
        # fromage=1 = posted in last 24 hours only
        url = f"https://www.indeed.com/jobs?q={requests.utils.quote(query)}&sort=date&fromage=1"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("div.job_seen_beacon")[:8]:
            title_el   = card.select_one("h2.jobTitle span")
            company_el = card.select_one("span[data-testid='company-name']")
            link_el    = card.select_one("a[data-jk]")
            if title_el and company_el and link_el:
                jk = link_el.get("data-jk", "")
                jobs.append({"title": title_el.get_text(strip=True),
                             "company": company_el.get_text(strip=True),
                             "link": f"https://www.indeed.com/viewjob?jk={jk}",
                             "source": "Indeed",
                             "date": datetime.date.today().isoformat(),
                             "id": f"indeed_{jk}"})
    except Exception as e:
        print(f"  Indeed error: {e}")
    return jobs

def search_linkedin(query):
    jobs = []
    try:
        url = (f"https://www.linkedin.com/jobs/search/?keywords={requests.utils.quote(query)}"
               f"&sortBy=DD&f_TPR=r86400")
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("div.base-card")[:8]:
            title_el   = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            link_el    = card.select_one("a.base-card__full-link")
            if title_el and company_el and link_el:
                link = link_el.get("href", "").split("?")[0]
                uid  = link.split("-")[-1] if link else str(random.randint(10000, 99999))
                jobs.append({"title": title_el.get_text(strip=True),
                             "company": company_el.get_text(strip=True),
                             "link": link, "source": "LinkedIn",
                             "date": datetime.date.today().isoformat(),
                             "id": f"li_{uid}"})
    except Exception as e:
        print(f"  LinkedIn error: {e}")
    return jobs

def handshake_link():
    """Single consolidated Handshake search link for all FRP terms."""
    encoded = requests.utils.quote("finance rotational program 2027")
    return {"title": 'Finance Rotational Programs 2027 — Search on Handshake',
            "company": "Multiple companies — click to browse",
            "link": f"https://joinhandshake.com/jobs/?query={encoded}&job_type=JOB",
            "source": "Handshake",
            "date": datetime.date.today().isoformat(),
            "id": "hs_frp_2027"}

# ── Classify new vs known programs ────────────────────────────────────────────
def classify_jobs(jobs):
    companies     = load_json(COMPANIES_FILE, [])
    known_map     = {c["company"].lower(): c for c in companies}  # name → full record
    known_names   = set(known_map.keys())
    known_jobs, new_programs = [], []

    for job in jobs:
        co = job.get("company", "").lower()
        if "multiple" in co or "handshake" in co:
            known_jobs.append(job)
            continue

        matched = next(
            (known_map[k] for k in known_names if k in co or co in k), None
        )
        if matched:
            # Replace scraped link with the company's direct careers page
            job = {**job,
                   "link":    matched["link"],
                   "program": matched.get("program", job.get("title", "")),
                   "note":    f"Apply directly at {matched['company']}"}
            known_jobs.append(job)
        else:
            # Unknown company — keep the source link (LinkedIn/Indeed)
            new_programs.append(job)

    return known_jobs, new_programs

# ── Deadline alerts ───────────────────────────────────────────────────────────
def get_deadline_alerts(days_ahead=7):
    companies  = load_json(COMPANIES_FILE, [])
    app_status = load_json(STATUS_FILE, {})
    today      = datetime.date.today()
    alerts     = []

    for co in companies:
        closes = co.get("closesMonth", "").lower()
        num    = MONTH_TO_NUM.get(closes)
        if not num:
            continue
        # Use next occurrence of that month
        year = today.year if num >= today.month else today.year + 1
        try:
            close_date = datetime.date(year, num, 1)
        except ValueError:
            continue

        days_left = (close_date - today).days
        if 0 <= days_left <= days_ahead:
            status = app_status.get(str(co["id"]), {}).get("status", "Not Applied")
            if status in ("Not Applied",):   # only alert if not yet applied
                alerts.append({**co, "days_left": days_left, "close_date": close_date.isoformat()})

    alerts.sort(key=lambda x: x["days_left"])
    return alerts

# ── Weekly summary ────────────────────────────────────────────────────────────
def get_weekly_summary():
    app_status = load_json(STATUS_FILE, {})
    companies  = load_json(COMPANIES_FILE, [])
    today      = datetime.date.today()

    counts = {"Applied": 0, "First Round": 0, "Second Round": 0,
              "Offer": 0, "Rejected": 0, "Not Applied": 0}
    closing_soon = []

    for co in companies:
        cid    = str(co["id"])
        status = app_status.get(cid, {}).get("status", "Not Applied")
        counts[status] = counts.get(status, 0) + 1

        closes = co.get("closesMonth", "").lower()
        num    = MONTH_TO_NUM.get(closes)
        if num:
            year = today.year if num >= today.month else today.year + 1
            try:
                close_date = datetime.date(year, num, 1)
                days_left  = (close_date - today).days
                if 0 <= days_left <= 14 and status == "Not Applied":
                    closing_soon.append({**co, "days_left": days_left})
            except ValueError:
                pass

    closing_soon.sort(key=lambda x: x["days_left"])
    return counts, closing_soon[:10]

# ── Main scan ─────────────────────────────────────────────────────────────────
def scan_all():
    seen          = set(load_json(SEEN_FILE, []))
    applied_cos   = already_applied_companies()   # companies you've already acted on
    today         = datetime.date.today().isoformat()
    new_jobs, errors = [], []

    for term in SEARCH_TERMS:
        print(f"  Scanning: {term}")
        found = []
        try:
            found += search_indeed(term)
            time.sleep(random.uniform(2, 4))
            found += search_linkedin(term)
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            errors.append(str(e))

        for job in found:
            # Skip if already seen in a previous run
            if job["id"] in seen:
                continue
            # Skip if posted on a different day (stale result slipping through)
            if job.get("date") and job["date"] != today:
                continue
            # Skip if you've already applied to this company
            co = job.get("company", "").lower()
            if any(k in co or co in k for k in applied_cos):
                continue
            # Skip if title doesn't look like a rotational/development program
            if not is_rotational(job.get("title", "")):
                continue
            seen.add(job["id"])
            new_jobs.append(job)

    # Add one consolidated Handshake link at the end (not per search term)
    hs = handshake_link()
    if hs["id"] not in seen:
        seen.add(hs["id"])
        new_jobs.append(hs)

    save_json(SEEN_FILE, list(seen))

    known_jobs, new_progs = classify_jobs(new_jobs)

    existing_jobs = load_json(NEW_JOBS_FILE, [])
    save_json(NEW_JOBS_FILE, (known_jobs + existing_jobs)[:200])

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
    save_json(ACTIVITY_LOG, log[:90])
    return entry

# ── Email builders ────────────────────────────────────────────────────────────
def _job_rows(jobs):
    rows = []
    for j in jobs:
        # Use program name if available (known companies), else scraped title
        display_title = j.get("program") or j.get("title", "")
        # Link label: known companies say "Apply at X", new programs say source
        if j.get("note"):
            link_label = f"Apply at {j['company'].split('(')[0].strip()} →"
        else:
            link_label = f"View on {j['source']} →"
        rows.append(f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <strong>{display_title}</strong><br>
            <span style="color:#666">{j['company']}</span>
          </td>
          <td style="padding:10px;border-bottom:1px solid #eee;color:#888">{j['source']}</td>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <a href="{j['link']}" style="color:#1d4ed8">{link_label}</a>
          </td>
        </tr>""")
    return "".join(rows)

def _deadline_rows(alerts):
    return "".join(f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <strong>{a['company']}</strong><br>
            <span style="color:#666;font-size:13px">{a['program']}</span>
          </td>
          <td style="padding:10px;border-bottom:1px solid #eee;color:#dc2626;font-weight:bold">
            {a['days_left']} day{'s' if a['days_left'] != 1 else ''} left
          </td>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <a href="{a['link']}" style="color:#1d4ed8">Apply →</a>
          </td>
        </tr>""" for a in alerts)

def send_daily_email(new_jobs, new_programs, deadline_alerts):
    if not EMAIL_PASS:
        print("  GMAIL_APP_PASSWORD not set — skipping email.")
        return False, "GMAIL_APP_PASSWORD not set"
    if not new_jobs and not new_programs and not deadline_alerts:
        print("  Nothing to report — no email sent.")
        return False, None

    today_str = datetime.date.today().strftime("%B %d, %Y")
    subject_parts = []
    if new_jobs:        subject_parts.append(f"{len(new_jobs)} new jobs")
    if new_programs:    subject_parts.append(f"{len(new_programs)} new programs")
    if deadline_alerts: subject_parts.append(f"{len(deadline_alerts)} deadlines soon")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"FRP Scanner — {', '.join(subject_parts)} ({today_str})"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    jobs_section = ""
    if new_jobs:
        jobs_section = f"""
        <h3 style="margin:20px 0 10px;color:#1e293b">New Job Postings ({len(new_jobs)})</h3>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px">
          <thead><tr style="background:#eff6ff">
            <th style="padding:10px;text-align:left">Role / Company</th>
            <th style="padding:10px;text-align:left">Source</th>
            <th style="padding:10px;text-align:left">Link</th>
          </tr></thead>
          <tbody>{_job_rows(new_jobs)}</tbody>
        </table>"""

    progs_section = ""
    if new_programs:
        progs_section = f"""
        <h3 style="margin:20px 0 10px;color:#1e293b">New Programs Discovered ({len(new_programs)})</h3>
        <p style="font-size:13px;color:#64748b;margin-bottom:8px">Not in your original 100 — worth checking out!</p>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px">
          <thead><tr style="background:#f0fdf4">
            <th style="padding:10px;text-align:left">Role / Company</th>
            <th style="padding:10px;text-align:left">Source</th>
            <th style="padding:10px;text-align:left">Link</th>
          </tr></thead>
          <tbody>{_job_rows(new_programs)}</tbody>
        </table>"""

    deadline_section = ""
    if deadline_alerts:
        deadline_section = f"""
        <h3 style="margin:20px 0 10px;color:#dc2626">Deadlines in 7 Days ({len(deadline_alerts)})</h3>
        <p style="font-size:13px;color:#64748b;margin-bottom:8px">You have NOT applied to these yet — act now!</p>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px">
          <thead><tr style="background:#fef2f2">
            <th style="padding:10px;text-align:left">Company / Program</th>
            <th style="padding:10px;text-align:left">Time Left</th>
            <th style="padding:10px;text-align:left">Link</th>
          </tr></thead>
          <tbody>{_deadline_rows(deadline_alerts)}</tbody>
        </table>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto">
      <div style="background:#0f172a;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">FRP Daily Scan</h2>
        <p style="color:#94a3b8;margin:4px 0 0">{today_str}</p>
      </div>
      <div style="padding:20px;background:#f8fafc;border-radius:0 0 8px 8px">
        <p>Hey Diego — here's your daily FRP update.</p>
        {deadline_section}
        {jobs_section}
        {progs_section}
      </div>
    </body></html>"""

    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"  Daily email sent to {EMAIL_TO}")
        return True, None
    except Exception as e:
        print(f"  Email failed: {e}")
        return False, str(e)

def send_weekly_email():
    if not EMAIL_PASS:
        return False, "GMAIL_APP_PASSWORD not set"

    counts, closing_soon = get_weekly_summary()
    today_str = datetime.date.today().strftime("%B %d, %Y")

    def stat_card(label, value, color):
        return f"""<td style="text-align:center;padding:16px;background:white;border-radius:8px;margin:4px">
          <div style="font-size:28px;font-weight:bold;color:{color}">{value}</div>
          <div style="font-size:12px;color:#64748b;margin-top:4px">{label}</div>
        </td>"""

    closing_rows = "".join(f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #eee"><strong>{c['company']}</strong></td>
          <td style="padding:10px;border-bottom:1px solid #eee;color:#dc2626">{c['days_left']} days</td>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <a href="{c['link']}" style="color:#1d4ed8">Apply →</a>
          </td>
        </tr>""" for c in closing_soon)

    closing_section = ""
    if closing_soon:
        closing_section = f"""
        <h3 style="color:#dc2626;margin:24px 0 10px">Closing in 14 Days</h3>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px">
          <thead><tr style="background:#fef2f2">
            <th style="padding:10px;text-align:left">Company</th>
            <th style="padding:10px;text-align:left">Days Left</th>
            <th style="padding:10px;text-align:left">Link</th>
          </tr></thead>
          <tbody>{closing_rows}</tbody>
        </table>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto">
      <div style="background:#0f172a;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">FRP Weekly Summary</h2>
        <p style="color:#94a3b8;margin:4px 0 0">Week of {today_str}</p>
      </div>
      <div style="padding:20px;background:#f8fafc;border-radius:0 0 8px 8px">
        <h3 style="color:#1e293b;margin:0 0 16px">Your Application Pipeline</h3>
        <table style="width:100%;border-spacing:8px;border-collapse:separate">
          <tr>
            {stat_card("Applied", counts.get("Applied",0), "#1d4ed8")}
            {stat_card("First Round", counts.get("First Round",0), "#7c3aed")}
            {stat_card("Second Round", counts.get("Second Round",0), "#0891b2")}
            {stat_card("Offers", counts.get("Offer",0), "#16a34a")}
            {stat_card("Rejected", counts.get("Rejected",0), "#dc2626")}
          </tr>
        </table>
        {closing_section}
        <p style="margin-top:24px;color:#94a3b8;font-size:12px">
          Not Applied: {counts.get("Not Applied",0)} programs remaining to explore.
        </p>
      </div>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"FRP Weekly Summary — {today_str}"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"  Weekly summary sent to {EMAIL_TO}")
        return True, None
    except Exception as e:
        print(f"  Weekly email failed: {e}")
        return False, str(e)

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"=== FRP Scanner — {datetime.datetime.now()} ===")
    new_jobs, new_programs, scan_errors = scan_all()
    deadline_alerts = get_deadline_alerts(days_ahead=7)
    if deadline_alerts:
        print(f"  {len(deadline_alerts)} deadline alert(s) to send.")

    email_sent, email_error = send_daily_email(new_jobs, new_programs, deadline_alerts)

    # Send weekly summary every Sunday (weekday 6)
    if datetime.date.today().weekday() == 6:
        print("  Sending weekly summary...")
        send_weekly_email()

    log_activity(new_jobs, new_programs, email_sent, email_error, scan_errors)
    print("Done.")
