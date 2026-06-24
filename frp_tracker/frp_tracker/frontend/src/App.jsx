import { useState, useEffect } from "react";
import companies from "./data/companies.json";
import "./App.css";

const STATUS_OPTIONS = ["Not Applied", "Applied", "First Round", "Final Round", "Offer", "Rejected"];
const STATUS_META = {
  "Not Applied": { color: "#6b7280", bg: "#f3f4f6", label: "Not Applied" },
  "Applied":     { color: "#1d4ed8", bg: "#dbeafe", label: "Applied" },
  "First Round": { color: "#92400e", bg: "#fef3c7", label: "First Round" },
  "Final Round": { color: "#7c3aed", bg: "#ede9fe", label: "Final Round" },
  "Offer":       { color: "#065f46", bg: "#d1fae5", label: "Offer" },
  "Rejected":    { color: "#991b1b", bg: "#fee2e2", label: "Rejected" },
};

const SECTORS = ["All", ...Array.from(new Set(companies.map(c => c.sector))).sort()];
const MONTHS  = ["All","January","February","March","April","May","June","July","August","September","October","November","December"];

function loadApps() {
  try { return JSON.parse(localStorage.getItem("frp_apps") || "{}"); }
  catch { return {}; }
}
function saveApps(apps) { localStorage.setItem("frp_apps", JSON.stringify(apps)); }

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const diff = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  return diff;
}

export default function App() {
  const [apps, setApps]           = useState(loadApps);
  const [tab, setTab]             = useState("tracker");
  const [sector, setSector]       = useState("All");
  const [statusF, setStatusF]     = useState("All");
  const [search, setSearch]       = useState("");
  const [openMonth, setOpenMonth] = useState("All");
  const [modal, setModal]         = useState(null);
  const [noteText, setNoteText]   = useState("");
  const [expandedNotes, setExpandedNotes] = useState({});

  useEffect(() => { saveApps(apps); }, [apps]);

  const updateApp = (id, field, value) =>
    setApps(prev => ({ ...prev, [id]: { ...(prev[id] || {}), [field]: value } }));

  const openModal = (id) => { setModal(id); setNoteText(apps[id]?.notes || ""); };
  const saveNote  = () => { updateApp(modal, "notes", noteText); setModal(null); };

  const filtered = companies.filter(c => {
    const app  = apps[c.id] || {};
    const st   = app.status || "Not Applied";
    return (sector    === "All" || c.sector === sector)
        && (statusF   === "All" || st === statusF)
        && (openMonth === "All" || c.opensMonth === openMonth)
        && (search    === ""   || c.company.toLowerCase().includes(search.toLowerCase()) || c.program.toLowerCase().includes(search.toLowerCase()));
  });

  const total   = companies.length;
  const applied = companies.filter(c => (apps[c.id]?.status || "Not Applied") !== "Not Applied").length;
  const offers  = companies.filter(c => apps[c.id]?.status === "Offer").length;
  const urgent  = companies.filter(c => {
    const d = daysUntil(apps[c.id]?.deadline);
    return d !== null && d >= 0 && d <= 7 && (apps[c.id]?.status || "Not Applied") === "Not Applied";
  }).length;

  const pct = Math.round((applied / total) * 100);

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-icon">🎯</div>
          <div>
            <div className="logo-text">FRP Tracker</div>
            <div className="logo-sub">2027 Cycle</div>
          </div>
        </div>

        <nav>
          {[
            ["tracker", "📋", "Tracker"],
            ["stats",   "📊", "Stats"],
          ].map(([k, icon, label]) => (
            <button key={k} className={`nav-btn ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>
              <span className="nav-icon">{icon}</span>
              {label}
            </button>
          ))}
        </nav>

        <div className="sidebar-progress">
          <div className="sp-label">
            <span>Overall Progress</span>
            <span className="sp-pct">{pct}%</span>
          </div>
          <div className="sp-track">
            <div className="sp-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="sp-sub">{applied} of {total} programs touched</div>
        </div>

        <div className="sidebar-footer">
          <div className="sf-name">Diego Sorto Taipe</div>
          <div className="sf-sub">UVA McIntire · 2027</div>
        </div>
      </aside>

      {/* Main */}
      <main className="main">

        {/* TRACKER */}
        {tab === "tracker" && (
          <>
            <div className="page-header">
              <div>
                <h1>Application Tracker</h1>
                <p className="muted">100 Finance Rotational Programs — update your status as you go</p>
              </div>
            </div>

            {/* KPI cards */}
            <div className="kpi-row">
              <div className="kpi-card">
                <div className="kpi-val" style={{ color: "#185FA5" }}>{total}</div>
                <div className="kpi-label">Total Programs</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-val" style={{ color: "#1d4ed8" }}>{applied}</div>
                <div className="kpi-label">In Progress</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-val" style={{ color: "#065f46" }}>{offers}</div>
                <div className="kpi-label">Offers</div>
              </div>
              <div className="kpi-card urgent-kpi">
                <div className="kpi-val" style={{ color: urgent > 0 ? "#b91c1c" : "#6b7280" }}>{urgent}</div>
                <div className="kpi-label">Deadlines This Week</div>
              </div>
            </div>

            {/* Filters */}
            <div className="filter-bar">
              <div className="search-wrap">
                <span className="search-icon">🔍</span>
                <input
                  className="search-input"
                  placeholder="Search company or program…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
                {search && <button className="search-clear" onClick={() => setSearch("")}>✕</button>}
              </div>

              <div className="filter-group">
                <label>Sector</label>
                <select value={sector} onChange={e => setSector(e.target.value)}>
                  {SECTORS.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>

              <div className="filter-group">
                <label>Status</label>
                <select value={statusF} onChange={e => setStatusF(e.target.value)}>
                  <option value="All">All Statuses</option>
                  {STATUS_OPTIONS.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>

              <div className="filter-group">
                <label>Opens</label>
                <select value={openMonth} onChange={e => setOpenMonth(e.target.value)}>
                  {MONTHS.map(m => <option key={m}>{m}</option>)}
                </select>
              </div>

              {(sector !== "All" || statusF !== "All" || openMonth !== "All" || search) && (
                <button className="clear-filters" onClick={() => { setSector("All"); setStatusF("All"); setOpenMonth("All"); setSearch(""); }}>
                  Clear filters
                </button>
              )}
            </div>

            <div className="results-count">{filtered.length} program{filtered.length !== 1 ? "s" : ""}</div>

            {/* Table */}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Program</th>
                    <th>Sector</th>
                    <th>Window</th>
                    <th>Status</th>
                    <th>Deadline</th>
                    <th>Notes</th>
                    <th>Apply</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(c => {
                    const app  = apps[c.id] || {};
                    const st   = app.status || "Not Applied";
                    const meta = STATUS_META[st];
                    const days = daysUntil(app.deadline);
                    const deadlineUrgent = days !== null && days >= 0 && days <= 7;
                    const deadlinePast   = days !== null && days < 0;

                    return (
                      <tr key={c.id} className={st === "Rejected" ? "row-rejected" : ""}>
                        <td className="company-name">{c.company}</td>
                        <td className="prog-name">{c.program}</td>
                        <td><span className="sector-tag">{c.sector}</span></td>
                        <td className="window-cell">
                          <span className="month-open">{c.opensMonth?.slice(0,3)}</span>
                          <span className="month-arrow">→</span>
                          <span className="month-close">{c.closesMonth?.slice(0,3)}</span>
                        </td>
                        <td>
                          <select
                            className="status-pill"
                            style={{ color: meta.color, background: meta.bg, borderColor: meta.color + "44" }}
                            value={st}
                            onChange={e => updateApp(c.id, "status", e.target.value)}
                          >
                            {STATUS_OPTIONS.map(s => <option key={s}>{s}</option>)}
                          </select>
                        </td>
                        <td>
                          <div className="deadline-wrap">
                            <input
                              type="date"
                              className={`date-input ${deadlineUrgent ? "urgent" : ""} ${deadlinePast ? "past" : ""}`}
                              value={app.deadline || ""}
                              onChange={e => updateApp(c.id, "deadline", e.target.value)}
                            />
                            {deadlineUrgent && <span className="deadline-badge">{days === 0 ? "Today!" : `${days}d`}</span>}
                            {deadlinePast   && <span className="deadline-badge past-badge">Passed</span>}
                          </div>
                        </td>
                        <td>
                          {app.notes ? (
                            <button className="note-btn has-note" onClick={() => openModal(c.id)} title={app.notes}>
                              📝 Edit note
                            </button>
                          ) : (
                            <button className="note-btn" onClick={() => openModal(c.id)}>+ Add note</button>
                          )}
                        </td>
                        <td>
                          <a href={c.link} target="_blank" rel="noreferrer" className="apply-btn">
                            Apply →
                          </a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {filtered.length === 0 && (
                <div className="empty">
                  <p>No programs match your filters.</p>
                  <button className="clear-filters" style={{ marginTop: 12 }} onClick={() => { setSector("All"); setStatusF("All"); setOpenMonth("All"); setSearch(""); }}>
                    Clear filters
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        {/* STATS */}
        {tab === "stats" && (
          <>
            <div className="page-header">
              <h1>Your Pipeline</h1>
              <p className="muted">A snapshot of where things stand across all 100 programs</p>
            </div>

            {/* Big progress ring replacement — horizontal progress bar */}
            <div className="pipeline-bar-card">
              <div className="pipeline-bar-header">
                <span className="pipeline-bar-title">Overall Progress</span>
                <span className="pipeline-bar-pct">{pct}%</span>
              </div>
              <div className="pipeline-track">
                <div className="pipeline-fill" style={{ width: `${pct}%` }} />
              </div>
              <div className="pipeline-bar-sub">{applied} programs started · {total - applied} remaining</div>
            </div>

            {/* Status breakdown */}
            <div className="status-breakdown">
              <h2 className="section-title">By Status</h2>
              <div className="status-grid">
                {STATUS_OPTIONS.map(s => {
                  const count = companies.filter(c => (apps[c.id]?.status || "Not Applied") === s).length;
                  const meta  = STATUS_META[s];
                  const p     = Math.round((count / total) * 100);
                  return (
                    <div
                      key={s}
                      className={`status-card ${statusF === s ? "active-filter" : ""}`}
                      onClick={() => { setStatusF(prev => prev === s ? "All" : s); setTab("tracker"); }}
                      style={{ borderColor: count > 0 ? meta.color + "55" : "#eee", cursor: "pointer" }}
                    >
                      <div className="sc-top">
                        <span className="sc-label" style={{ color: meta.color }}>{s}</span>
                        <span className="sc-count" style={{ color: meta.color }}>{count}</span>
                      </div>
                      <div className="sc-track">
                        <div className="sc-fill" style={{ width: `${p}%`, background: meta.color }} />
                      </div>
                      <div className="sc-pct">{p}% of programs</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Sector breakdown */}
            <div className="sector-breakdown-card">
              <h2 className="section-title">By Sector</h2>
              {SECTORS.filter(s => s !== "All").map(s => {
                const scos = companies.filter(c => c.sector === s);
                const appd = scos.filter(c => (apps[c.id]?.status || "Not Applied") !== "Not Applied").length;
                const p    = Math.round((appd / scos.length) * 100);
                return (
                  <div className="sector-row" key={s}>
                    <div className="sector-left">
                      <span className="sector-name">{s}</span>
                      <span className="sector-count">{appd}/{scos.length}</span>
                    </div>
                    <div className="sector-bar-track">
                      <div className="sector-bar-fill" style={{ width: `${p}%` }} />
                    </div>
                    <span className="sector-pct">{p}%</span>
                  </div>
                );
              })}
            </div>

            {/* Upcoming deadlines */}
            {(() => {
              const upcoming = companies
                .map(c => ({ ...c, app: apps[c.id] || {} }))
                .filter(c => {
                  const d = daysUntil(c.app.deadline);
                  return d !== null && d >= 0 && d <= 14;
                })
                .sort((a, b) => new Date(a.app.deadline) - new Date(b.app.deadline));

              if (!upcoming.length) return null;
              return (
                <div className="upcoming-card">
                  <h2 className="section-title">Upcoming Deadlines <span className="deadline-count">{upcoming.length}</span></h2>
                  {upcoming.map(c => {
                    const days = daysUntil(c.app.deadline);
                    const st   = c.app.status || "Not Applied";
                    const meta = STATUS_META[st];
                    return (
                      <div key={c.id} className={`deadline-row ${days <= 3 ? "deadline-hot" : ""}`}>
                        <div className="deadline-info">
                          <span className="deadline-company">{c.company}</span>
                          <span className="deadline-prog">{c.program}</span>
                        </div>
                        <span className="deadline-status" style={{ color: meta.color, background: meta.bg }}>{st}</span>
                        <span className={`deadline-days ${days <= 3 ? "hot" : ""}`}>
                          {days === 0 ? "Today!" : `${days}d`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </>
        )}
      </main>

      {/* Notes Modal */}
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Notes</h3>
              <span className="modal-company">{companies.find(c => c.id === modal)?.company}</span>
            </div>
            <textarea
              value={noteText}
              onChange={e => setNoteText(e.target.value)}
              placeholder="Add contacts, interview tips, links, anything helpful…"
              rows={7}
              autoFocus
            />
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setModal(null)}>Cancel</button>
              <button className="btn-save" onClick={saveNote}>Save note</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
