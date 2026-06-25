import { useState, useEffect } from "react";
import companies from "./data/companies.json";
import newJobsData from "./data/new_jobs.json";
import "./App.css";

const STATUS_OPTIONS = ["Not Applied", "Applied", "First Round", "Final Round", "Offer", "Rejected"];
const STATUS_COLORS  = {
  "Not Applied": "#888",
  "Applied":     "#185FA5",
  "First Round": "#BA7517",
  "Final Round": "#854F0B",
  "Offer":       "#1D9E75",
  "Rejected":    "#A32D2D",
};

const SECTORS = ["All", ...Array.from(new Set(companies.map(c => c.sector))).sort()];
const MONTHS  = ["All","January","February","March","April","May","June","July","August","September","October","November","December"];

function loadApps() {
  try { return JSON.parse(localStorage.getItem("frp_apps") || "{}"); }
  catch { return {}; }
}
function saveApps(apps) {
  localStorage.setItem("frp_apps", JSON.stringify(apps));
}
function loadJobs() {
  return newJobsData;
}

export default function App() {
  const [apps, setApps]         = useState(loadApps);
  const [newJobs, setNewJobs]   = useState(loadJobs);
  const [tab, setTab]           = useState("tracker");
  const [sector, setSector]     = useState("All");
  const [statusF, setStatusF]   = useState("All");
  const [search, setSearch]     = useState("");
  const [openMonth, setOpenMonth] = useState("All");
  const [modal, setModal]       = useState(null); // company id
  const [noteText, setNoteText] = useState("");

  useEffect(() => { saveApps(apps); }, [apps]);

  const updateApp = (id, field, value) => {
    setApps(prev => ({ ...prev, [id]: { ...(prev[id] || {}), [field]: value } }));
  };

  const openModal = (id) => {
    setModal(id);
    setNoteText(apps[id]?.notes || "");
  };
  const saveNote = () => {
    updateApp(modal, "notes", noteText);
    setModal(null);
  };

  const filtered = companies.filter(c => {
    const app   = apps[c.id] || {};
    const st    = app.status || "Not Applied";
    const matchS  = sector   === "All" || c.sector === sector;
    const matchSt = statusF  === "All" || st === statusF;
    const matchM  = openMonth === "All" || c.opensMonth === openMonth;
    const matchQ  = search === "" ||
      c.company.toLowerCase().includes(search.toLowerCase()) ||
      c.program.toLowerCase().includes(search.toLowerCase());
    return matchS && matchSt && matchM && matchQ;
  });

  // Stats
  const total    = companies.length;
  const applied  = companies.filter(c => (apps[c.id]?.status || "Not Applied") !== "Not Applied").length;
  const offers   = companies.filter(c => apps[c.id]?.status === "Offer").length;
  const openNow  = companies.filter(c => {
    const mo = ["July","August","June"].includes(c.opensMonth);
    return mo && (apps[c.id]?.status || "Not Applied") === "Not Applied";
  }).length;

  return (
    <div className="app">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-icon">🎯</span>
          <span className="logo-text">FRP Tracker</span>
        </div>
        <nav>
          {[["tracker","Tracker"],["feed","Job Feed"],["stats","Stats"]].map(([k,v]) => (
            <button key={k} className={`nav-btn ${tab===k?"active":""}`} onClick={() => setTab(k)}>{v}</button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <p>Diego Sorto Taipe</p>
          <p className="muted">UVA McIntire · 2027</p>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main">

        {/* ── TRACKER TAB ── */}
        {tab === "tracker" && (
          <>
            <div className="page-header">
              <h1>Application Tracker</h1>
              <p className="muted">Track all 100 FRP programs in one place</p>
            </div>

            {/* Stats row */}
            <div className="stat-row">
              {[["Total Programs", total, "#185FA5"],["Applied", applied, "#BA7517"],["Offers", offers, "#1D9E75"],["Opens Soon", openNow, "#854F0B"]].map(([l,v,c]) => (
                <div className="stat-card" key={l}>
                  <p className="stat-label">{l}</p>
                  <p className="stat-val" style={{color:c}}>{v}</p>
                </div>
              ))}
            </div>

            {/* Filters */}
            <div className="filters">
              <input className="search-input" placeholder="Search company or program…" value={search} onChange={e=>setSearch(e.target.value)} />
              <select value={sector} onChange={e=>setSector(e.target.value)}>
                {SECTORS.map(s=><option key={s}>{s}</option>)}
              </select>
              <select value={statusF} onChange={e=>setStatusF(e.target.value)}>
                <option value="All">All Statuses</option>
                {STATUS_OPTIONS.map(s=><option key={s}>{s}</option>)}
              </select>
              <select value={openMonth} onChange={e=>setOpenMonth(e.target.value)}>
                {MONTHS.map(m=><option key={m}>{m}</option>)}
              </select>
            </div>

            {/* Table */}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Program</th>
                    <th>Sector</th>
                    <th>Opens</th>
                    <th>Closes</th>
                    <th>Status</th>
                    <th>Deadline</th>
                    <th>Notes</th>
                    <th>Link</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(c => {
                    const app = apps[c.id] || {};
                    const st  = app.status || "Not Applied";
                    return (
                      <tr key={c.id}>
                        <td className="company-name">{c.company}</td>
                        <td className="prog-name">{c.program}</td>
                        <td><span className="sector-tag">{c.sector}</span></td>
                        <td>{c.opensMonth}</td>
                        <td>{c.closesMonth}</td>
                        <td>
                          <select
                            className="status-select"
                            style={{color: STATUS_COLORS[st], borderColor: STATUS_COLORS[st]}}
                            value={st}
                            onChange={e => updateApp(c.id, "status", e.target.value)}
                          >
                            {STATUS_OPTIONS.map(s=><option key={s}>{s}</option>)}
                          </select>
                        </td>
                        <td>
                          <input
                            type="date"
                            className="date-input"
                            value={app.deadline || ""}
                            onChange={e => updateApp(c.id, "deadline", e.target.value)}
                          />
                        </td>
                        <td>
                          <button className="note-btn" onClick={() => openModal(c.id)}>
                            {app.notes ? "📝 Edit" : "+ Add"}
                          </button>
                        </td>
                        <td>
                          <a href={c.link} target="_blank" rel="noreferrer" className="link-btn">Apply →</a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {filtered.length === 0 && <p className="empty">No programs match your filters.</p>}
            </div>
          </>
        )}

        {/* ── JOB FEED TAB ── */}
        {tab === "feed" && (
          <>
            <div className="page-header">
              <h1>New Job Feed</h1>
              <p className="muted">Populated by the daily Python scanner — run <code>python backend/scanner.py</code> to refresh</p>
            </div>
            {newJobs.length === 0 ? (
              <div className="empty-feed">
                <p>🔍 No jobs scanned yet.</p>
                <p className="muted">Run the scanner to populate this feed:</p>
                <code>cd backend && python scanner.py</code>
              </div>
            ) : (
              <div className="job-grid">
                {newJobs.map((j,i) => (
                  <div className="job-card" key={i}>
                    <div className="job-header">
                      <span className="job-source">{j.source}</span>
                      <span className="job-date">{j.date}</span>
                    </div>
                    <p className="job-title">{j.title}</p>
                    <p className="job-company">{j.company}</p>
                    <a href={j.link} target="_blank" rel="noreferrer" className="job-link">View posting →</a>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* ── STATS TAB ── */}
        {tab === "stats" && (
          <>
            <div className="page-header">
              <h1>Your Stats</h1>
              <p className="muted">Application pipeline overview</p>
            </div>
            <div className="stats-grid">
              {STATUS_OPTIONS.map(s => {
                const count = companies.filter(c => (apps[c.id]?.status || "Not Applied") === s).length;
                const pct   = Math.round((count/total)*100);
                return (
                  <div className="stats-card" key={s}>
                    <p className="stats-label">{s}</p>
                    <p className="stats-count" style={{color: STATUS_COLORS[s]}}>{count}</p>
                    <div className="progress-track">
                      <div className="progress-fill" style={{width:`${pct}%`, background: STATUS_COLORS[s]}} />
                    </div>
                    <p className="stats-pct">{pct}%</p>
                  </div>
                );
              })}
            </div>
            <div className="sector-breakdown">
              <h2>By Sector</h2>
              {SECTORS.filter(s=>s!=="All").map(s => {
                const scos    = companies.filter(c=>c.sector===s);
                const appd    = scos.filter(c=>(apps[c.id]?.status||"Not Applied")!=="Not Applied").length;
                return (
                  <div className="sector-row" key={s}>
                    <span className="sector-name">{s}</span>
                    <div className="sector-bar-track">
                      <div className="sector-bar-fill" style={{width:`${Math.round((appd/scos.length)*100)}%`}} />
                    </div>
                    <span className="sector-count">{appd}/{scos.length}</span>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </main>

      {/* ── Notes Modal ── */}
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>Notes — {companies.find(c=>c.id===modal)?.company}</h3>
            <textarea
              value={noteText}
              onChange={e => setNoteText(e.target.value)}
              placeholder="Add notes, contacts, interview tips…"
              rows={6}
            />
            <div className="modal-actions">
              <button className="btn-save" onClick={saveNote}>Save</button>
              <button className="btn-cancel" onClick={() => setModal(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
