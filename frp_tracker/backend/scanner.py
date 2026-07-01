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
STATUS_FILE       = FRONTEND / "app_status.json"

MONTH_TO_NUM = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12
}

SEARCH_TERMS = [
    '"finance rotational program" 2027',
    '"finance leadership development program" 2027',
    '"finance leadership development" program 2027',
    '"financial management program" 2027',
    '"finance rotation program" 2027',
    '"financial rotational program" 2027',
    '"finance development program" 2027',
    '"finance associate program" 2027',
    '"finance analyst program" 2027',
    '"FDP" finance rotational 2027',
    '"FLDP" finance 2027',
    'finance rotational program "new grad" 2027',
    'finance leadership program "full time" 2027',
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
    # Don't gate on "2027" being in the title — job boards rarely include the year
    # in the title text even when the role is for the 2027 cohort. The search query
    # already scopes to 2027, so any returned result is implicitly 2027.
    t = title.lower()
    return any(kw in t for kw in ROTATIONAL_KEYWORDS)

def known_companies():
    companies = load_json(COMPANIES_FILE, [])
    return {c["company"].lower() for c in companies}

def already_applied_companies():
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
        url = f"https://www.indeed.com/jobs?q={requests.utils.quote(query)}&sort=date&fromage=7"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("div.job_seen_beacon")[:8]:
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
    """Use LinkedIn's guest jobs API — returns real HTML fragments unlike the
    JS-rendered main search page which always comes back empty to scrapers."""
    jobs = []
    try:
        # Past-week filter (r604800 = 604800 seconds = 7 days) so we catch anything
        # posted in the last week, not just the last 24h which is too narrow for slow
        # posting cycles on rotational programs.
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={requests.utils.quote(query)}"
            "&location=United+States&geoId=103644278"
            "&f_TPR=r604800&start=0"
        )
        resp = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("li")[:10]:
            title_el   = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            link_el    = card.select_one("a.base-card__full-link")
            if not (title_el and company_el and link_el):
                continue
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

def search_ziprecruiter(query):
    jobs = []
    try:
        url = f"https://www.ziprecruiter.com/candidate/search?search={requests.utils.quote(query)}&days=7"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("article.job_result")[:8]:
            title_el   = card.select_one("h2.title")
            company_el = card.select_one("a.company_name")
            link_el    = card.select_one("a.job_link")
            if title_el and company_el and link_el:
                link = link_el.get("href", "")
                uid  = abs(hash(link)) % 10**8
                jobs.append({
                    "title":   title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True),
                    "link":    link,
                    "source":  "ZipRecruiter",
                    "date":    datetime.date.today().isoformat(),
                    "id":      f"zr_{uid}",
                })
    except Exception as e:
        print(f"  ZipRecruiter error: {e}")
    return jobs

def search_simplyhired(query):
    jobs = []
    try:
        url = f"https://www.simplyhired.com/search?q={requests.utils.quote(query)}&t=1"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("div[data-testid='searchSerpJob']")[:8]:
            title_el   = card.select_one("h3[data-testid='searchSerpJobTitle']")
            company_el = card.select_one("span[data-testid='searchSerpJobCompanyName']")
            link_el    = card.select_one("a")
            if title_el and company_el and link_el:
                href = link_el.get("href", "")
                link = f"https://www.simplyhired.com{href}" if href.startswith("/") else href
                uid  = abs(hash(link)) % 10**8
                jobs.append({
                    "title":   title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True),
                    "link":    link,
                    "source":  "SimplyHired",
                    "date":    datetime.date.today().isoformat(),
                    "id":      f"sh_{uid}",
                })
    except Exception as e:
        print(f"  SimplyHired error: {e}")
    return jobs

def check_company_pages():
    """Check each company's own career page for confirmed 2027 FRP postings.
    Requires specific class-of-2027 phrases to avoid false positives from
    copyright notices or unrelated date mentions."""
    companies  = load_json(COMPANIES_FILE, [])
    app_status = load_json(STATUS_FILE, {})
    applied_ids = {cid for cid, v in app_status.items()
                   if v.get("status") in {"Applied","First Round","Second Round","Offer","Rejected"}}
    jobs = []
    # Must find one of these specific phrases — not just "2027" appearing anywhere
    trigger_phrases = [
        "class of 2027",
        "2027 program",
        "2027 cohort",
        "for 2027",
        "2027 graduate",
        "graduating in 2027",
        "start in 2027",
        "starting in 2027",
        "beginning 2027",
        "summer 2027",
        "fall 2027",
        "apply for 2027",
        "applications for 2027",
    ]

    for co in companies:
        if str(co["id"]) in applied_ids:
            continue
        try:
            resp = requests.get(co["link"], headers=HEADERS, timeout=8)
            text = resp.text.lower()
            if any(phrase in text for phrase in trigger_phrases):
                uid = f"cp_{co['id']}"
                jobs.append({
                    "title":   co["program"] + " — Class of 2027",
                    "company": co["company"],
                    "link":    co["link"],
                    "source":  "Company Page",
                    "date":    datetime.date.today().isoformat(),
                    "id":      uid,
                    "program": co["program"],
                    "note":    f"Apply directly at {co['company']}",
                })
                print(f"  [Company Page] {co['company']} — confirmed 2027 posting")
            time.sleep(random.uniform(1, 2))
        except Exception:
            pass
    return jobs

def handshake_link():
    encoded = requests.utils.quote("finance rotational program 2027")
    return {
        "title":   "Finance Rotational Programs 2027 — Search on Handshake",
        "company": "Multiple companies — click to browse",
        "link":    f"https://joinhandshake.com/jobs/?query={encoded}&job_type=JOB",
        "source":  "Handshake",
        "date":    datetime.date.today().isoformat(),
        "id":      "hs_frp_2027",
    }

# ── Classify new vs known programs ────────────────────────────────────────────
def classify_jobs(jobs):
    companies   = load_json(COMPANIES_FILE, [])
    known_map   = {c["company"].lower(): c for c in companies}
    known_names = set(known_map.keys())
    known_jobs, new_programs = [], []

    for job in jobs:
        co = job.get("company", "").lower()
        if "multiple" in co or "handshake" in co:
            known_jobs.append(job)
            continue
        matched = next(
            (known_map[k] for k in known_names
             if (k in co and len(k) >= 5) or (co in k and len(co) >= 5)), None
        )
        if matched:
            job = {
                **job,
                "link":    matched["link"],
                "program": matched.get("program", job.get("title", "")),
                "note":    f"Apply directly at {matched['company']}",
            }
            known_jobs.append(job)
        else:
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
        year = today.year if num >= today.month else today.year + 1
        try:
            close_date = datetime.date(year, num, 1)
        except ValueError:
            continue
        days_left = (close_date - today).days
        if 0 <= days_left <= days_ahead:
            status = app_status.get(str(co["id"]), {}).get("status", "Not Applied")
            if status == "Not Applied":
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
    seen        = set(load_json(SEEN_FILE, []))
    applied_cos = already_applied_companies()
    today       = datetime.date.today().isoformat()
    new_jobs, errors = [], []

    for term in SEARCH_TERMS:
        print(f"  Scanning: {term}")
        found = []
        try:
            found += search_indeed(term)
            time.sleep(random.uniform(2, 4))
            found += search_linkedin(term)
            time.sleep(random.uniform(2, 4))
            found += search_ziprecruiter(term)
            time.sleep(random.uniform(2, 4))
            found += search_simplyhired(term)
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            errors.append(str(e))

        for job in found:
            if job["id"] in seen:
                continue
            if job.get("date") and job["date"] != today:
                continue
            co = job.get("company", "").lower()
            if any(k in co or co in k for k in applied_cos):
                continue
            if not is_rotational(job.get("title", "")):
                continue
            seen.add(job["id"])
            new_jobs.append(job)

    # Check company career pages — don't add cp_ IDs to seen so they're re-checked daily
    print("  Checking company career pages...")
    company_page_jobs = check_company_pages()
    cp_ids_already = {j["id"] for j in new_jobs}
    for job in company_page_jobs:
        if job["id"] not in cp_ids_already:
            new_jobs.append(job)

    save_json(SEEN_FILE, list(seen))  # only job-board IDs in seen

    known_jobs, new_progs = classify_jobs(new_jobs)
    hs = handshake_link()

    # Overwrite new_jobs.json each run — prevents stale accumulation and merge conflicts
    save_json(NEW_JOBS_FILE, known_jobs[:200])

    existing_progs = load_json(NEW_PROGRAMS_FILE, [])
    existing_ids   = {p["id"] for p in existing_progs}
    fresh_progs    = [p for p in new_progs if p["id"] not in existing_ids]
    save_json(NEW_PROGRAMS_FILE, (fresh_progs + existing_progs)[:500])

    print(f"  Found {len(known_jobs)} new job postings, {len(fresh_progs)} new programs.")
    return known_jobs, fresh_progs, errors, hs

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
        display_title = j.get("program") or j.get("title", "")
        if j.get("note"):
            link_label = "Apply at {} →".format(j["company"].split("(")[0].strip())
        else:
            link_label = "View on {} →".format(j["source"])
        rows.append(
            "<tr>"
            "<td style='padding:10px;border-bottom:1px solid #eee'>"
            "<strong>{}</strong><br>"
            "<span style='color:#666'>{}</span>"
            "</td>"
            "<td style='padding:10px;border-bottom:1px solid #eee;color:#888'>{}</td>"
            "<td style='padding:10px;border-bottom:1px solid #eee'>"
            "<a href='{}' style='color:#1d4ed8'>{}</a>"
            "</td>"
            "</tr>".format(
                display_title, j["company"], j["source"], j["link"], link_label
            )
        )
    return "".join(rows)

def _deadline_rows(alerts):
    rows = []
    for a in alerts:
        s = "s" if a["days_left"] != 1 else ""
        rows.append(
            "<tr>"
            "<td style='padding:10px;border-bottom:1px solid #eee'>"
            "<strong>{}</strong><br>"
            "<span style='color:#666;font-size:13px'>{}</span>"
            "</td>"
            "<td style='padding:10px;border-bottom:1px solid #eee;color:#dc2626;font-weight:bold'>"
            "{} day{} left"
            "</td>"
            "<td style='padding:10px;border-bottom:1px solid #eee'>"
            "<a href='{}' style='color:#1d4ed8'>Apply →</a>"
            "</td>"
            "</tr>".format(a["company"], a["program"], a["days_left"], s, a["link"])
        )
    return "".join(rows)

def send_daily_email(new_jobs, new_programs, deadline_alerts):
    if not EMAIL_PASS:
        print("  GMAIL_APP_PASSWORD not set — skipping email.")
        return False, "GMAIL_APP_PASSWORD not set"
    # Always send so you know the scanner ran, even if nothing new was found

    today_str = datetime.date.today().strftime("%B %d, %Y")
    subject_parts = []
    if new_jobs:        subject_parts.append(f"{len(new_jobs)} new jobs")
    if new_programs:    subject_parts.append(f"{len(new_programs)} new programs")
    if deadline_alerts: subject_parts.append(f"{len(deadline_alerts)} deadlines soon")
    summary_label = ", ".join(subject_parts) if subject_parts else "No new postings today"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "FRP Scanner — {} ({})".format(summary_label, today_str)
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    jobs_section = ""
    if new_jobs:
        jobs_section = (
            "<h3 style='margin:20px 0 10px;color:#1e293b'>New Job Postings ({})</h3>"
            "<table style='width:100%;border-collapse:collapse;background:white;border-radius:8px'>"
            "<thead><tr style='background:#eff6ff'>"
            "<th style='padding:10px;text-align:left'>Role / Company</th>"
            "<th style='padding:10px;text-align:left'>Source</th>"
            "<th style='padding:10px;text-align:left'>Link</th>"
            "</tr></thead>"
            "<tbody>{}</tbody>"
            "</table>"
        ).format(len(new_jobs), _job_rows(new_jobs))

    progs_section = ""
    if new_programs:
        progs_section = (
            "<h3 style='margin:20px 0 10px;color:#1e293b'>New Programs Discovered ({})</h3>"
            "<p style='font-size:13px;color:#64748b;margin-bottom:8px'>Not in your original 100 — worth checking out!</p>"
            "<table style='width:100%;border-collapse:collapse;background:white;border-radius:8px'>"
            "<thead><tr style='background:#f0fdf4'>"
            "<th style='padding:10px;text-align:left'>Role / Company</th>"
            "<th style='padding:10px;text-align:left'>Source</th>"
            "<th style='padding:10px;text-align:left'>Link</th>"
            "</tr></thead>"
            "<tbody>{}</tbody>"
            "</table>"
        ).format(len(new_programs), _job_rows(new_programs))

    deadline_section = ""
    if deadline_alerts:
        deadline_section = (
            "<h3 style='margin:20px 0 10px;color:#dc2626'>Deadlines in 7 Days ({})</h3>"
            "<p style='font-size:13px;color:#64748b;margin-bottom:8px'>You have NOT applied to these yet — act now!</p>"
            "<table style='width:100%;border-collapse:collapse;background:white;border-radius:8px'>"
            "<thead><tr style='background:#fef2f2'>"
            "<th style='padding:10px;text-align:left'>Company / Program</th>"
            "<th style='padding:10px;text-align:left'>Time Left</th>"
            "<th style='padding:10px;text-align:left'>Link</th>"
            "</tr></thead>"
            "<tbody>{}</tbody>"
            "</table>"
        ).format(len(deadline_alerts), _deadline_rows(deadline_alerts))

    html = (
        "<html><body style='font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto'>"
        "<div style='background:#0f172a;padding:20px;border-radius:8px 8px 0 0'>"
        "<h2 style='color:white;margin:0'>FRP Daily Scan</h2>"
        "<p style='color:#94a3b8;margin:4px 0 0'>{}</p>"
        "</div>"
        "<div style='padding:20px;background:#f8fafc;border-radius:0 0 8px 8px'>"
        "<p>Hey Diego — here's your daily FRP update.</p>"
        "{}{}{}"
        "</div>"
        "</body></html>"
    ).format(today_str, deadline_section, jobs_section, progs_section)

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
        return (
            "<td style='text-align:center;padding:16px;background:white;border-radius:8px;margin:4px'>"
            "<div style='font-size:28px;font-weight:bold;color:{}'>{}</div>"
            "<div style='font-size:12px;color:#64748b;margin-top:4px'>{}</div>"
            "</td>"
        ).format(color, value, label)

    closing_rows = []
    for c in closing_soon:
        closing_rows.append(
            "<tr>"
            "<td style='padding:10px;border-bottom:1px solid #eee'><strong>{}</strong></td>"
            "<td style='padding:10px;border-bottom:1px solid #eee;color:#dc2626'>{} days</td>"
            "<td style='padding:10px;border-bottom:1px solid #eee'>"
            "<a href='{}' style='color:#1d4ed8'>Apply →</a>"
            "</td>"
            "</tr>".format(c["company"], c["days_left"], c["link"])
        )

    closing_section = ""
    if closing_soon:
        closing_section = (
            "<h3 style='color:#dc2626;margin:24px 0 10px'>Closing in 14 Days</h3>"
            "<table style='width:100%;border-collapse:collapse;background:white;border-radius:8px'>"
            "<thead><tr style='background:#fef2f2'>"
            "<th style='padding:10px;text-align:left'>Company</th>"
            "<th style='padding:10px;text-align:left'>Days Left</th>"
            "<th style='padding:10px;text-align:left'>Link</th>"
            "</tr></thead>"
            "<tbody>{}</tbody>"
            "</table>"
        ).format("".join(closing_rows))

    html = (
        "<html><body style='font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto'>"
        "<div style='background:#0f172a;padding:20px;border-radius:8px 8px 0 0'>"
        "<h2 style='color:white;margin:0'>FRP Weekly Summary</h2>"
        "<p style='color:#94a3b8;margin:4px 0 0'>Week of {}</p>"
        "</div>"
        "<div style='padding:20px;background:#f8fafc;border-radius:0 0 8px 8px'>"
        "<h3 style='color:#1e293b;margin:0 0 16px'>Your Application Pipeline</h3>"
        "<table style='width:100%;border-spacing:8px;border-collapse:separate'>"
        "<tr>{}{}{}{}{}</tr>"
        "</table>"
        "{}"
        "<p style='margin-top:24px;color:#94a3b8;font-size:12px'>Not Applied: {} programs remaining to explore.</p>"
        "</div>"
        "</body></html>"
    ).format(
        today_str,
        stat_card("Applied", counts.get("Applied", 0), "#1d4ed8"),
        stat_card("First Round", counts.get("First Round", 0), "#7c3aed"),
        stat_card("Second Round", counts.get("Second Round", 0), "#0891b2"),
        stat_card("Offers", counts.get("Offer", 0), "#16a34a"),
        stat_card("Rejected", counts.get("Rejected", 0), "#dc2626"),
        closing_section,
        counts.get("Not Applied", 0),
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "FRP Weekly Summary — {}".format(today_str)
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
    new_jobs, new_programs, scan_errors, handshake = scan_all()
    deadline_alerts = get_deadline_alerts(days_ahead=7)
    if deadline_alerts:
        print(f"  {len(deadline_alerts)} deadline alert(s) to send.")

    email_sent, email_error = send_daily_email(new_jobs + [handshake], new_programs, deadline_alerts)

    if datetime.date.today().weekday() == 6:
        print("  Sending weekly summary...")
        send_weekly_email()

    log_activity(new_jobs, new_programs, email_sent, email_error, scan_errors)
    print("Done.")
