import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend, PieChart, Pie, Cell,
} from "recharts";

const PIE_COLORS = ["#b91c1c", "#92400e", "#1e40af", "#065f46", "#4c1d95", "#374151", "#6b7280"];

export default function StatsPanel({ byCountry, byDay, byAffiliation, namedCasualties }) {

  // Pivot byCountry into per-country killed/wounded/missing
  const countryMap = {};
  byCountry.forEach(row => {
    if (!countryMap[row.Country]) countryMap[row.Country] = { Country: row.Country, Killed: 0, Wounded: 0, Missing: 0 };
    countryMap[row.Country][row.CasualtyType] = (countryMap[row.Country][row.CasualtyType] ?? 0) + row.TotalCasualties;
  });
  const countryData = Object.values(countryMap)
    .sort((a, b) => (b.Killed + b.Wounded + b.Missing) - (a.Killed + a.Wounded + a.Missing))
    .slice(0, 12);

  // Affiliation pie
  const affiliationData = byAffiliation.map(r => ({ name: r.Affiliation, value: r.Total }));

  return (
    <div className="stats-wrapper">

      {/* ── Row 1: Timeline chart ── */}
      <section className="chart-section">
        <h2 className="chart-title">Incidents &amp; Killed Per Day</h2>
        <p className="chart-subtitle">Daily count of logged incidents and total confirmed/reported killed</p>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={byDay} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="IncidentDate" tick={{ fontSize: 11, fill: "#6b7280" }} />
            <YAxis tick={{ fontSize: 11, fill: "#6b7280" }} />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #e5e7eb" }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone" dataKey="TotalKilled" name="Killed"
              stroke="#b91c1c" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }}
            />
            <Line
              type="monotone" dataKey="IncidentCount" name="Incidents"
              stroke="#1e40af" strokeWidth={2} strokeDasharray="5 4"
              dot={{ r: 4 }} activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </section>

      {/* ── Row 2: Country bar + Affiliation pie ── */}
      <div className="chart-row-2">
        <section className="chart-section">
          <h2 className="chart-title">Casualties by Country</h2>
          <p className="chart-subtitle">Killed, wounded and missing per nationality (top 12)</p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={countryData} layout="vertical" margin={{ left: 16, right: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: "#6b7280" }} />
              <YAxis dataKey="Country" type="category" tick={{ fontSize: 11, fill: "#374151" }} width={120} />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #e5e7eb" }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Killed"  fill="#b91c1c" stackId="a" name="Killed" />
              <Bar dataKey="Wounded" fill="#f59e0b" stackId="a" name="Wounded" />
              <Bar dataKey="Missing" fill="#3b82f6" stackId="a" name="Missing" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="chart-section">
          <h2 className="chart-title">Killed by Affiliation</h2>
          <p className="chart-subtitle">Breakdown of confirmed/reported deaths</p>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={affiliationData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
                labelLine={true}
              >
                {affiliationData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #e5e7eb" }}
                formatter={(val, name) => [val.toLocaleString(), name]}
              />
            </PieChart>
          </ResponsiveContainer>
        </section>
      </div>

      {/* ── Row 3: Named casualties table ── */}
      {namedCasualties.length > 0 && (
        <section className="chart-section">
          <h2 className="chart-title">Named Individuals</h2>
          <p className="chart-subtitle">Identified casualties with verified or reported status</p>
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Age</th>
                  <th>Affiliation</th>
                  <th>Nationality</th>
                  <th>Type</th>
                  <th>Date</th>
                  <th>Location</th>
                  <th>Status</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {namedCasualties.map((c, i) => (
                  <tr key={i}>
                    <td className="td-name">{c.FullName}</td>
                    <td>{c.Age ?? "—"}</td>
                    <td>{c.Affiliation}</td>
                    <td>{c.Nationality ?? "—"}</td>
                    <td>
                      <span className={`status-pill status-pill--${c.CasualtyType?.toLowerCase()}`}>
                        {c.CasualtyType}
                      </span>
                    </td>
                    <td>{c.IncidentDate}</td>
                    <td>{c.Location}</td>
                    <td>
                      <span className={`status-pill status-pill--${c.VerificationStatus?.toLowerCase()}`}>
                        {c.VerificationStatus}
                      </span>
                    </td>
                    <td className="td-notes">{c.Notes ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
