import { useState } from "react";

const TYPE_COLORS = {
  "Airstrike":      "#b91c1c",
  "Missile Strike": "#92400e",
  "Drone Strike":   "#1e40af",
  "Naval Attack":   "#065f46",
  "Ground Attack":  "#4c1d95",
  "Other":          "#374151",
};

export default function IncidentFeed({ incidents }) {
  const [search, setSearch]         = useState("");
  const [filterType, setFilterType] = useState("All");
  const [filterParty, setFilterParty] = useState("All");

  const types   = ["All", ...new Set(incidents.map(i => i.IncidentType).filter(Boolean))];
  const parties = ["All", ...new Set(incidents.map(i => i.AttackingParty).filter(Boolean))];

  const filtered = incidents.filter(inc => {
    const matchSearch = !search ||
      inc.Description?.toLowerCase().includes(search.toLowerCase()) ||
      inc.Location?.toLowerCase().includes(search.toLowerCase());
    const matchType  = filterType  === "All" || inc.IncidentType   === filterType;
    const matchParty = filterParty === "All" || inc.AttackingParty === filterParty;
    return matchSearch && matchType && matchParty;
  });

  return (
    <div className="feed-wrapper">
      {/* Filters */}
      <div className="filters">
        <input
          className="filter-input"
          type="text"
          placeholder="Search incidents…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select
          className="filter-select"
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
        >
          {types.map(t => <option key={t}>{t}</option>)}
        </select>
        <select
          className="filter-select"
          value={filterParty}
          onChange={e => setFilterParty(e.target.value)}
        >
          {parties.map(p => <option key={p}>{p}</option>)}
        </select>
        <span className="filter-count">{filtered.length} incident{filtered.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Timeline */}
      <div className="timeline">
        {filtered.length === 0 && (
          <p className="empty-state">No incidents match your filters.</p>
        )}
        {filtered.map((inc, idx) => (
          <div className="incident-card" key={inc.IncidentID ?? idx}>
            <div className="incident-card-left">
              <div className="incident-date">{inc.IncidentDate}</div>
              <div className="incident-dot" />
              {idx < filtered.length - 1 && <div className="incident-line" />}
            </div>
            <div className="incident-card-body">
              <div className="incident-card-header">
                <span
                  className="incident-type-badge"
                  style={{ backgroundColor: TYPE_COLORS[inc.IncidentType] ?? "#374151" }}
                >
                  {inc.IncidentType}
                </span>
                {inc.AttackingParty && (
                  <span className="incident-party">↑ {inc.AttackingParty}</span>
                )}
                {inc.TargetType && (
                  <span className="incident-target">Target: {inc.TargetType}</span>
                )}
              </div>

              <div className="incident-location">📍 {inc.Location}</div>
              <p className="incident-description">{inc.Description}</p>

              <div className="incident-casualties">
                {inc.TotalKilled  > 0 && <CasTag label="Killed"  n={inc.TotalKilled}  color="#b91c1c" />}
                {inc.TotalWounded > 0 && <CasTag label="Wounded" n={inc.TotalWounded} color="#92400e" />}
                {inc.TotalMissing > 0 && <CasTag label="Missing" n={inc.TotalMissing} color="#1e40af" />}
                {inc.TotalKilled === 0 && inc.TotalWounded === 0 && inc.TotalMissing === 0 && (
                  <span className="cas-tag" style={{ backgroundColor: "#e5e7eb", color: "#6b7280" }}>
                    No casualty data
                  </span>
                )}
              </div>

              {inc.ReportedBy && (
                <div className="incident-source">Source: {inc.ReportedBy}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CasTag({ label, n, color }) {
  return (
    <span className="cas-tag" style={{ backgroundColor: color }}>
      {n} {label}
    </span>
  );
}
