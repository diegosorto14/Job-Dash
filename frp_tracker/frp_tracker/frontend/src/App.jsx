import { useState, useEffect } from "react";
import companies from "./data/companies.json";
import activityLogData from "./data/activity_log.json";
import newProgramsData from "./data/new_programs.json";
import "./App.css";

const STATUS_OPTIONS = ["Not Applied", "Applied", "First Round", "Final Round", "Offer", "Rejected"];
const STATUS_META = {
  "Not Applied": { color: "#6b7280", bg: "#f3f4f6" },
  "Applied":     { color: "#1d4ed8", bg: "#dbeafe" },
  "First Round": { color: "#92400e", bg: "#fef3c7" },
  "Final Round": { color: "#7c3aed", bg: "#ede9fe" },
  "Offer":       { color: "#065f46", bg: "#d1fae5" },
  "Rejected":    { color: "#991b1b", bg: "#fee2e2" },
};

const SECTORS = ["All", ...Array.from(new Set(companies.map(c => c.sector))).sort()];
const MONTHS  = ["All","January","February","March","April","May","June","July","August","September","October","November","December"];

function loadApps()   { try { return JSON.parse(localStorage.getItem("frp_apps")  || "{}"); } catch { return {}; } }
function saveApps(a)  { localStorage.setItem("frp_apps", JSON.stringify(a)); }
function loadAdded()  { try { return JSON.parse(localStorage.getItem("frp_added") || "[]"); } catch { return []; } }
function saveAdded(a) { localStorage.setItem("frp_added", JSON.stringify(a)); }

function daysUntil(dateStr) {
  if (!dateStr) return null;
  return Math.ceil((new Date(dateStr) - new Date()) / 86400000);
}

function fmt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

export default function App() {
  const [apps, setApps]           = useState(loadApps);
  const [added, setAdded]         = useState(loadAdded); // user-added programs from Discover
  const [tab, setTab]             = useState("tracker");
  const [sector, setSector]       = useState("All");
  const [statusF, setStatusF]     = useState("All");
  const [search, setSearch]       = useState("");
  const [openMonth, setOpenMonth] = useState("All");
  const [modal, setModal]         = useState(null);
  const [noteText, setNoteText]   = useState("");
  const [discoverSearch, setDiscoverSearch] = useState("");

  useEffect(() => { saveApps(apps); }, [apps]);
  useEffect(() => { saveAdded(added); }, [added]);

  const updateApp = (id, field, value) =>
    setApps(prev => ({ ...prev, [id]: { ...(prev[id] || {}), [field]: value } }));

  const openModal = (id) => { setModal(id); setNoteText(apps[id]?.notes || ""); };
  const saveNote  = () => { updateApp(modal, "notes", noteText); setModal(null); };

  // All programs = original 100 + user-added from Discover
  const allCompanies = [...companies, ...added];

  const filtered = allCompanies.filter(c => {
    const app  = apps[c.id] || {};
    const st   = app.status || "Not Applied";
    return (sector    === "All" || c.sector === sector)
        && (statusF   === "All" || st === statusF)
        && (openMonth === "All" || c.opensMonth === openMonth)
        && (search    === ""   || c.company.toLowerCase().includes(search.toLowerCase())
                               || c.program.toLowerCase().includes(search.toLowerCase()));
  });

  const total   = allCompanies.length;
  const applied = allCompanies.filter(c => (apps[c.id]?.status || "Not Applied") !== "Not Applied").length;
  const offers  = allCompanies.filter(c => apps[c.id]?.status === "Offer").length;
  const urgent  = allCompanies.filter(c => {
    const d = daysUntil(apps[c.id]?.deadline);
    return d !== null && d >= 0 && d <= 7 && (apps[c.id]?.status || "Not Applied") === "Not Applied";
  }).length;
  const pct = Math.round((applied / total) * 100);

  // Discover: programs not already added
  const addedIds   = new Set(added.map(a => a.id));
  const origIds    = new Set(companies.map(c => String(c.id)));
  const toDiscover = newProgramsData.filter(p =>
    !addedIds.has(p.id) && !origIds.has(p.id) &&
    (discoverSearch === "" ||
      p.company.toLowerCase().includes(discoverSearch.toLowerCase()) ||
      p.title.toLowerCase().includes(discoverSearch.toLowerCase()))
  );

  const addProgram = (prog) => {
    const newEntry = {
      id:         prog.id,
      company:    prog.company,
      program:    prog.title,
      sector:     "Discovered",
      opensMonth: "Unknown",
      closesMonth:"Unknown",
      link:       prog.link,
      discovered: true,
    };
    setAdded(prev => [newEntry, ...prev]);
  };

  // Activity log stats
  const totalScans  = activityLogData.length;
  const lastScan    = activityLogData[0];
  const emailsSent  = activityLogData.filter(e => e.email_sent).length;
  const totalFound  = activityLogData.reduce((s, e) => s + (e.new_jobs || 0), 0);
  const totalNewPro = activityLogData.reduce((s, e) => s + (e.new_programs || 0), 0);

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
            ["tracker",  "📋", "Tracker",  null],
            ["discover", "🔭", "Discover", toDiscover.length || null],
            ["activity", "📬", "Activity", null],
            ["stats",    "📊", "Stats",    null],
          ].map(([k, icon, label, badge]) => (
            <button key={k} className={`nav-btn ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>
              <span className="nav-icon">{icon}</span>
              <span className="nav-label">{label}</span>
              {badge ? <span className="nav-badge">{badge}</span> : null}
            </button>
          ))}
        </nav>

        <div className="sidebar-progress">
          <div className="sp-label">
            <span>Overall Progress</span>
            <span className="sp-pct">{pct}%</span>
          </div>
          <div className="sp-track"><div className="sp-fill" style={{ width: `${pct}%` }} /></div>
          <div className="sp-sub">{applied} of {total} programs touched</div>
        </div>

        <div className="sidebar-footer">
          <div className="sf-name">Diego Sorto Taipe</div>
          <div className="sf-sub">UVA McIntire · 2027</div>
        </div>
      </aside>

      {/* Main */}
      <main className="main">

        {/* ── TRACKER ── */}
        {tab === "tracker" && (
          <>
            <div className="page-header">
              <h1>Application Tracker</h1>
              <p className="muted">{total} Finance Rotational Programs — update your status as you go</p>
            </div>

            <div className="kpi-row">
              {[
                ["Total", total, "#185FA5", false],
                ["In Progress", applied, "#1d4ed8", false],
                ["Offers", offers, "#065f46", false],
                ["Due This Week", urgent, urgent > 0 ? "#b91c1c" : "#6b7280", urgent > 0],
              ].map(([label, val, color, warn]) => (
                <div key={label} className={`kpi-card ${warn ? "urgent-kpi" : ""}`}>
                  <div className="kpi-val" style={{ color }}>{val}</div>
                  <div className="kpi-label">{label}</div>
                </div>
              ))}
            </div>

            <div className="filter-bar">
              <div className="search-wrap">
                <span className="search-icon">🔍</span>
                <input className="search-input" placeholder="Search company or program…" value={search} onChange={e => setSearch(e.target.value)} />
                {search && <button className="search-clear" onClick={() => setSearch("")}>✕</button>}
              </div>
              {[
                ["Sector",  sector,    setSector,    SECTORS],
                ["Opens",   openMonth, setOpenMonth, MONTHS],
              ].map(([lbl, val, set, opts]) => (
                <div className="filter-group" key={lbl}>
                  <label>{lbl}</label>
                  <select value={val} onChange={e => set(e.target.value)}>
                    {opts.map(o => <option key={o}>{o}</option>)}
                  </select>
                </div>
              ))}
              <div className="filter-group">
                <label>Status</label>
                <select value={statusF} onChange={e => setStatusF(e.target.value)}>
                  <option value="All">All Statuses</option>
                  {STATUS_OPTIONS.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
              {(sector !== "All" || statusF !== "All" || openMonth !== "All" || search) && (
                <button className="clear-filters" onClick={() => { setSector("All"); setStatusF("All"); setOpenMonth("All"); setSearch(""); }}>Clear</button>
              )}
            </div>

            <div className="results-count">{filtered.length} program{filtered.length !== 1 ? "s" : ""}</div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Company</th><th>Program</th><th>Sector</th>
                    <th>Window</th><th>Status</th><th>Deadline</th>
                    <th>Notes</th><th>Apply</th>
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
                      <tr key={c.id} className={`${st === "Rejected" ? "row-rejected" : ""} ${c.discovered ? "row-discovered" : ""}`}>
                        <td className="company-name">
                          {c.company}
                          {c.discovered && <span className="discovered-badge">New</span>}
                        </td>
                        <td className="prog-name">{c.program}</td>
                        <td><span className={`sector-tag ${c.discovered ? "sector-new" : ""}`}>{c.sector}</span></td>
                        <td className="window-cell">
                          <span className="month-open">{c.opensMonth?.slice(0,3)}</span>
                          <span className="month-arrow">→</span>
                          <span className="month-close">{c.closesMonth?.slice(0,3)}</span>
                        </td>
                        <td>
                          <select className="status-pill" style={{ color: meta.color, background: meta.bg, borderColor: meta.color + "44" }} value={st} onChange={e => updateApp(c.id, "status", e.target.value)}>
                            {STATUS_OPTIONS.map(s => <option key={s}>{s}</option>)}
                          </select>
                        </td>
                        <td>
                          <div className="deadline-wrap">
                            <input type="date" className={`date-input ${deadlineUrgent ? "urgent" : ""} ${deadlinePast ? "past" : ""}`} value={app.deadline || ""} onChange={e => updateApp(c.id, "deadline", e.target.value)} />
                            {deadlineUrgent && <span className="deadline-badge">{days === 0 ? "Today!" : `${days}d`}</span>}
                            {deadlinePast   && <span className="deadline-badge past-badge">Passed</span>}
                          </div>
                        </td>
                        <td>
                          <button className={`note-btn ${app.notes ? "has-note" : ""}`} onClick={() => openModal(c.id)}>
                            {app.notes ? "📝 Edit" : "+ Note"}
                          </button>
                        </td>
                        <td>
                          <a href={c.link} target="_blank" rel="noreferrer" className="apply-btn">Apply →</a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {filtered.length === 0 && (
                <div className="empty">
                  <p>No programs match your filters.</p>
                  <button className="clear-filters" style={{ marginTop: 12 }} onClick={() => { setSector("All"); setStatusF("All"); setOpenMonth("All"); setSearch(""); }}>Clear filters</button>
                </div>
              )}
            </div>
          </>
        )}

        {/* ── DISCOVER ── */}
        {tab === "discover" && (
          <>
            <div className="page-header">
              <h1>Discover New Programs</h1>
              <p className="muted">Programs found by the scanner that aren't in your original 100 — add any to your tracker</p>
            </div>

            {newProgramsData.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🔭</div>
                <h3>No new programs found yet</h3>
                <p>Run the scanner to start discovering programs beyond the original 100:</p>
                <code>cd backend && python scanner.py</code>
                <p className="muted" style={{ marginTop: 12 }}>The scanner searches Indeed, LinkedIn, and Handshake daily for new FRP postings.</p>
              </div>
            ) : (
              <>
                <div className="discover-toolbar">
                  <div className="search-wrap" style={{ flex: 1, maxWidth: 360 }}>
                    <span className="search-icon">🔍</span>
                    <input className="search-input" placeholder="Search discovered programs…" value={discoverSearch} onChange={e => setDiscoverSearch(e.target.value)} />
                    {discoverSearch && <button className="search-clear" onClick={() => setDiscoverSearch("")}>✕</button>}
                  </div>
                  <span className="results-count" style={{ margin: 0 }}>{toDiscover.length} new · {addedIds.size} added to tracker</span>
                </div>

                <div className="discover-grid">
                  {toDiscover.map((p, i) => (
                    <div className="discover-card" key={p.id || i}>
                      <div className="dc-header">
                        <span className="dc-source">{p.source}</span>
                        <span className="dc-date">{fmt(p.date)}</span>
                      </div>
                      <div className="dc-company">{p.company}</div>
                      <div className="dc-title">{p.title}</div>
                      <div className="dc-actions">
                        <a href={p.link} target="_blank" rel="noreferrer" className="dc-view">View posting →</a>
                        <button className="dc-add" onClick={() => addProgram(p)}>+ Add to Tracker</button>
                      </div>
                    </div>
                  ))}
                  {toDiscover.length === 0 && discoverSearch && (
                    <div className="empty" style={{ gridColumn: "1/-1" }}>No results for "{discoverSearch}"</div>
                  )}
                </div>

                {added.length > 0 && (
                  <div className="added-section">
                    <h2 className="section-title">Added to Your Tracker ({added.length})</h2>
                    <div className="added-list">
                      {added.map(p => (
                        <div className="added-row" key={p.id}>
                          <div className="added-info">
                            <span className="added-company">{p.company}</span>
                            <span className="added-prog">{p.program}</span>
                          </div>
                          <span className={`status-pill-sm`} style={{ color: STATUS_META[apps[p.id]?.status || "Not Applied"].color, background: STATUS_META[apps[p.id]?.status || "Not Applied"].bg }}>
                            {apps[p.id]?.status || "Not Applied"}
                          </span>
                          <a href={p.link} target="_blank" rel="noreferrer" className="apply-btn">Apply →</a>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* ── ACTIVITY ── */}
        {tab === "activity" && (
          <>
            <div className="page-header">
              <h1>Scanner Activity</h1>
              <p className="muted">Every time the scanner runs, it logs here — including emails sent and programs found</p>
            </div>

            {/* Activity KPIs */}
            <div className="kpi-row">
              {[
                ["Total Scans",     totalScans,  "#185FA5"],
                ["Emails Sent",     emailsSent,  "#065f46"],
                ["Jobs Found",      totalFound,  "#1d4ed8"],
                ["New Programs",    totalNewPro, "#7c3aed"],
              ].map(([label, val, color]) => (
                <div key={label} className="kpi-card">
                  <div className="kpi-val" style={{ color }}>{val}</div>
                  <div className="kpi-label">{label}</div>
                </div>
              ))}
            </div>

            {activityLogData.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📬</div>
                <h3>No scan history yet</h3>
                <p>Run the scanner to start tracking activity:</p>
                <code>cd backend && python scanner.py</code>
                <p className="muted" style={{ marginTop: 12 }}>
                  Set up a daily cron job so this runs automatically every morning:<br/>
                  <code style={{ marginTop: 8, display: "inline-block" }}>0 8 * * * cd /path/to/backend && python scanner.py</code>
                </p>
              </div>
            ) : (
              <>
                {lastScan && (
                  <div className="last-scan-card">
                    <div className="ls-left">
                      <div className="ls-label">Last Scan</div>
                      <div className="ls-date">{fmt(lastScan.date)}</div>
                      <div className="ls-time">{fmtTime(lastScan.ts)}</div>
                    </div>
                    <div className="ls-stats">
                      <div className="ls-stat"><span className="ls-num">{lastScan.new_jobs}</span><span className="ls-slabel">jobs found</span></div>
                      <div className="ls-stat"><span className="ls-num">{lastScan.new_programs}</span><span className="ls-slabel">new programs</span></div>
                      <div className="ls-stat">
                        <span className={`ls-email ${lastScan.email_sent ? "sent" : "not-sent"}`}>
                          {lastScan.email_sent ? "✅ Email sent" : lastScan.email_error ? `❌ ${lastScan.email_error}` : "— No email"}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                <h2 className="section-title" style={{ marginBottom: 12 }}>Scan History</h2>
                <div className="activity-list">
                  {activityLogData.map((entry, i) => (
                    <div key={i} className={`activity-row ${entry.email_sent ? "row-emailed" : ""}`}>
                      <div className="ar-date">
                        <div className="ar-day">{fmt(entry.date)}</div>
                        <div className="ar-time">{fmtTime(entry.ts)}</div>
                      </div>
                      <div className="ar-pills">
                        <span className="ar-pill jobs">{entry.new_jobs} jobs</span>
                        {entry.new_programs > 0 && <span className="ar-pill progs">{entry.new_programs} new programs</span>}
                        {entry.scan_errors?.length > 0 && <span className="ar-pill errors" title={entry.scan_errors.join("\n")}>{entry.scan_errors.length} error{entry.scan_errors.length > 1 ? "s" : ""}</span>}
                      </div>
                      <div className="ar-email">
                        {entry.email_sent
                          ? <span className="email-sent">✅ Email sent</span>
                          : entry.email_error
                            ? <span className="email-err" title={entry.email_error}>⚠ {entry.email_error.length > 30 ? entry.email_error.slice(0,30) + "…" : entry.email_error}</span>
                            : <span className="email-none">No email</span>
                        }
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {/* ── STATS ── */}
        {tab === "stats" && (
          <>
            <div className="page-header">
              <h1>Your Pipeline</h1>
              <p className="muted">A snapshot of where things stand across all {total} programs</p>
            </div>

            <div className="pipeline-bar-card">
              <div className="pipeline-bar-header">
                <span className="pipeline-bar-title">Overall Progress</span>
                <span className="pipeline-bar-pct">{pct}%</span>
              </div>
              <div className="pipeline-track"><div className="pipeline-fill" style={{ width: `${pct}%` }} /></div>
              <div className="pipeline-bar-sub">{applied} programs started · {total - applied} remaining</div>
            </div>

            <div className="status-breakdown">
              <h2 className="section-title">By Status</h2>
              <div className="status-grid">
                {STATUS_OPTIONS.map(s => {
                  const count = allCompanies.filter(c => (apps[c.id]?.status || "Not Applied") === s).length;
                  const meta  = STATUS_META[s];
                  const p     = Math.round((count / total) * 100);
                  return (
                    <div key={s} className="status-card" onClick={() => { setStatusF(prev => prev === s ? "All" : s); setTab("tracker"); }} style={{ borderColor: count > 0 ? meta.color + "55" : "#eee", cursor: "pointer" }}>
                      <div className="sc-top">
                        <span className="sc-label" style={{ color: meta.color }}>{s}</span>
                        <span className="sc-count" style={{ color: meta.color }}>{count}</span>
                      </div>
                      <div className="sc-track"><div className="sc-fill" style={{ width: `${p}%`, background: meta.color }} /></div>
                      <div className="sc-pct">{p}% of programs</div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="sector-breakdown-card">
              <h2 className="section-title">By Sector</h2>
              {SECTORS.filter(s => s !== "All").map(s => {
                const scos = allCompanies.filter(c => c.sector === s);
                const appd = scos.filter(c => (apps[c.id]?.status || "Not Applied") !== "Not Applied").length;
                const p    = Math.round((appd / scos.length) * 100);
                return (
                  <div className="sector-row" key={s}>
                    <div className="sector-left">
                      <span className="sector-name">{s}</span>
                      <span className="sector-count">{appd}/{scos.length}</span>
                    </div>
                    <div className="sector-bar-track"><div className="sector-bar-fill" style={{ width: `${p}%` }} /></div>
                    <span className="sector-pct">{p}%</span>
                  </div>
                );
              })}
            </div>

            {(() => {
              const upcoming = allCompanies.map(c => ({ ...c, app: apps[c.id] || {} }))
                .filter(c => { const d = daysUntil(c.app.deadline); return d !== null && d >= 0 && d <= 14; })
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
                        <span className={`deadline-days ${days <= 3 ? "hot" : ""}`}>{days === 0 ? "Today!" : `${days}d`}</span>
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
              <span className="modal-company">{allCompanies.find(c => c.id === modal)?.company}</span>
            </div>
            <textarea value={noteText} onChange={e => setNoteText(e.target.value)} placeholder="Add contacts, interview tips, links, anything helpful…" rows={7} autoFocus />
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
