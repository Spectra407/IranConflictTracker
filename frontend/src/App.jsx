import { useState, useEffect } from "react";
import IncidentFeed from "./components/IncidentFeed";
import StatsPanel from "./components/StatsPanel";
import "./App.css";

const API = process.env.REACT_APP_API_URL || "http://localhost:5000/api";

export default function App() {
  const [incidents, setIncidents]             = useState([]);
  const [summary, setSummary]                 = useState([]);
  const [byCountry, setByCountry]             = useState([]);
  const [byDay, setByDay]                     = useState([]);
  const [byAffiliation, setByAffiliation]     = useState([]);
  const [namedCasualties, setNamedCasualties] = useState([]);
  const [loading, setLoading]                 = useState(true);
  const [error, setError]                     = useState(null);
  const [activeTab, setActiveTab]             = useState("incidents");

  useEffect(() => {
    const fetchWithRetry = async (url, retries = 3, delay = 5000) => {
      for (let i = 0; i < retries; i++) {
        try {
          const res = await fetch(url);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return await res.json();
        } catch (err) {
          if (i < retries - 1) {
            await new Promise(r => setTimeout(r, delay));
          } else {
            throw err;
          }
        }
      }
    };

    const load = async () => {
      try {
        const [inc, sum, byC, byD, byA, named] = await Promise.all([
          fetchWithRetry(`${API}/incidents`),
          fetchWithRetry(`${API}/casualties/summary`),
          fetchWithRetry(`${API}/casualties/by-country`),
          fetchWithRetry(`${API}/incidents/by-day`),
          fetchWithRetry(`${API}/casualties/by-affiliation`),
          fetchWithRetry(`${API}/named-casualties`),
        ]);
        setIncidents(inc);
        setSummary(sum);
        setByCountry(byC);
        setByDay(byD);
        setByAffiliation(byA);
        setNamedCasualties(named);
        setLoading(false);
      } catch (err) {
        setError("Could not connect to the API. The server may still be waking up — please refresh in 30 seconds.");
        setLoading(false);
      }
    };

    load();
  }, []);

  const totalKilled  = summary.find(s => s.CasualtyType === "Killed")?.Total  ?? 0;
  const totalWounded = summary.find(s => s.CasualtyType === "Wounded")?.Total ?? 0;
  const totalMissing = summary.find(s => s.CasualtyType === "Missing")?.Total ?? 0;

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-inner">
          <div className="header-left">
            <div className="header-badge">By Kenny Ly using data from NewsAPI</div>
            <h1 className="header-title">Iran Conflict Tracker</h1>
            <p className="header-subtitle">
              Casualty &amp; Incident Database — Iran–Israel–US Conflict, February 2026–Present
            </p>
          </div>
          <div className="header-right">
            <div className="header-updated">
              Last updated: {new Date().toLocaleDateString("en-CA")}
            </div>
          </div>
        </div>
      </header>

      {/* ── KPI Bar ── */}
      <div className="kpi-bar">
        <div className="kpi-bar-inner">
          <KPI label="Total Killed"     value={totalKilled.toLocaleString()}    color="var(--red)"   />
          <div className="kpi-divider" />
          <KPI label="Total Wounded"    value={totalWounded.toLocaleString()}   color="var(--amber)" />
          <div className="kpi-divider" />
          <KPI label="Total Missing"    value={totalMissing.toLocaleString()}   color="var(--blue)"  />
          <div className="kpi-divider" />
          <KPI label="Incidents Logged" value={incidents.length.toLocaleString()} color="var(--slate)" />
        </div>
      </div>

      {/* ── Nav Tabs ── */}
      <nav className="tabs">
        <div className="tabs-inner">
          <button
            className={`tab ${activeTab === "incidents" ? "tab--active" : ""}`}
            onClick={() => setActiveTab("incidents")}
          >
            Incident Feed
          </button>
          <button
            className={`tab ${activeTab === "stats" ? "tab--active" : ""}`}
            onClick={() => setActiveTab("stats")}
          >
            Casualty Statistics
          </button>
        </div>
      </nav>

      {/* ── Main Content ── */}
      <main className="main">
        {loading && (
          <div className="status-box">
            <div className="spinner" />
            <p>Loading data from database…</p>
          </div>
        )}
        {error && (
          <div className="status-box status-box--error">
            <p>⚠ {error}</p>
          </div>
        )}
        {!loading && !error && activeTab === "incidents" && (
          <IncidentFeed incidents={incidents} />
        )}
        {!loading && !error && activeTab === "stats" && (
          <StatsPanel
            byCountry={byCountry}
            byDay={byDay}
            byAffiliation={byAffiliation}
            namedCasualties={namedCasualties}
          />
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="footer">
        <div className="footer-inner">
          <p>
            Sources: Al Jazeera, Reuters, US CENTCOM, Iranian State Media, NBC, NPR.
            All figures provisional. Verification status noted per record.
          </p>
        </div>
      </footer>
    </div>
  );
}

function KPI({ label, value, color }) {
  return (
    <div className="kpi">
      <span className="kpi-value" style={{ color }}>{value}</span>
      <span className="kpi-label">{label}</span>
    </div>
  );
}
