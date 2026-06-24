# FRP Tracker — Diego Sorto Taipe
Finance Rotational Program tracker with daily job scanning and email alerts.

---

## Project Structure
```
frp_tracker/
├── frontend/          ← React dashboard (run in browser)
│   ├── src/
│   │   ├── App.jsx    ← Main dashboard
│   │   ├── App.css    ← Styles
│   │   └── data/
│   │       ├── companies.json   ← All 100 FRP companies pre-loaded
│   │       └── new_jobs.json    ← Populated by scanner (auto-created)
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
└── backend/
    ├── scanner.py         ← Daily job scanner + email alerter
    ├── requirements.txt
    ├── .env.example       ← Copy to .env and add your Gmail app password
    └── seen_jobs.json     ← Auto-created, tracks already-seen postings
```

---

## Setup (One Time)

### 1. Install Node.js
Download from https://nodejs.org (LTS version)

### 2. Install Python
Download from https://python.org (3.10+)

### 3. Set up the frontend
```bash
cd frp_tracker/frontend
npm install
```

### 4. Set up the backend
```bash
cd frp_tracker/backend
pip install -r requirements.txt
```

### 5. Set up Gmail App Password (for email alerts)
1. Go to https://myaccount.google.com/apppasswords
2. Create an app password for "Mail"
3. Copy the 16-character password
4. In the backend folder, copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
5. Open `.env` and replace `your_app_password_here` with your actual password:
   ```
   GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
   ```

---

## Running the Dashboard

```bash
cd frp_tracker/frontend
npm run dev
```
Then open **http://localhost:3000** in your browser.

Your application data is saved automatically in your browser's local storage — it persists between sessions.

---

## Running the Job Scanner

### Manually (anytime)
```bash
cd frp_tracker/backend
python scanner.py
```
This will:
- Search Indeed, LinkedIn, and Handshake for new FRP postings
- Save new jobs to `frontend/src/data/new_jobs.json`
- Email diego.sorto14@gmail.com with a summary

### Automatically every day (Mac/Linux)
Add a cron job to run it daily at 8am:

```bash
crontab -e
```
Add this line (update the path to match where you saved the project):
```
0 8 * * * cd /path/to/frp_tracker/backend && python scanner.py >> scanner.log 2>&1
```

### Automatically every day (Windows)
Use Task Scheduler:
1. Open Task Scheduler → Create Basic Task
2. Name: "FRP Scanner"
3. Trigger: Daily at 8:00 AM
4. Action: Start a Program
5. Program: `python`
6. Arguments: `C:\path\to\frp_tracker\backend\scanner.py`

---

## Dashboard Features

### Tracker Tab
- All 100 FRP companies pre-loaded with open/close months
- Update application status (Not Applied → Applied → First Round → Final Round → Offer / Rejected)
- Set deadline reminders
- Add notes per company (contacts, interview tips, etc.)
- Filter by sector, status, open month, or search by name

### Job Feed Tab
- Shows new postings found by the scanner
- Populated automatically when you run `python scanner.py`
- Click any posting to go directly to the application

### Stats Tab
- Visual breakdown of your pipeline by status
- Progress by sector
- See where you're concentrating vs. missing

---

## Notes
- LinkedIn and Handshake may require login for full results — the scanner provides direct search URLs you can click
- The scanner respects rate limits with randomized delays to avoid being blocked
- All application data is stored locally in your browser — nothing is sent to any server
