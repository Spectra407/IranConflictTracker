"""
backend/app.py
──────────────
Flask API for the Iran Conflict Tracker React frontend.
Serves data from SQL Server via the existing views.

Install:  pip install flask flask-cors pyodbc
Run:      python app.py
"""
import os

from flask import Flask, jsonify
from flask_cors import CORS
import pymssql

app = Flask(__name__)
CORS(app)   # allows React (localhost:3000) to call this API (localhost:5000)

# ── Database connection ────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

SQL_SERVER   = os.getenv("SQL_SERVER")
SQL_DATABASE = os.getenv("SQL_DATABASE")
SQL_USERNAME = os.getenv("SQL_USERNAME")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")

def get_db():
    return pymssql.connect(
        server=os.getenv("SQL_SERVER"),
        user=os.getenv("SQL_USERNAME"),
        password=os.getenv("SQL_PASSWORD"),
        database=os.getenv("SQL_DATABASE")
    )

def rows_to_dicts(cursor):
    """Convert pyodbc rows to a list of dicts using column names."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/api/incidents")
def get_incidents():
    """All incidents, newest first, with casualty counts."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            IncidentID,
            IncidentKey,
            CONVERT(VARCHAR, IncidentDate, 23) AS IncidentDate,
            Location,
            IncidentType,
            AttackingParty,
            TargetType,
            Description,
            TotalKilled,
            TotalWounded,
            TotalMissing,
            ReportedBy
        FROM vw_IncidentSummary
        ORDER BY IncidentDate DESC, IncidentID DESC
    """)
    data = rows_to_dicts(cursor)
    conn.close()
    return jsonify(data)


@app.route("/api/casualties/by-country")
def get_casualties_by_country():
    """Total killed/wounded/missing grouped by country."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            Country,
            CasualtyType,
            Affiliation,
            TotalCasualties
        FROM vw_CasualtiesByCountry
        WHERE Country IS NOT NULL
        ORDER BY TotalCasualties DESC
    """)
    data = rows_to_dicts(cursor)
    conn.close()
    return jsonify(data)


@app.route("/api/casualties/summary")
def get_casualties_summary():
    """Grand totals — killed, wounded, missing."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            CasualtyType,
            SUM(CasualtyCount) AS Total
        FROM Casualties
        GROUP BY CasualtyType
    """)
    data = rows_to_dicts(cursor)
    conn.close()
    return jsonify(data)


@app.route("/api/casualties/by-affiliation")
def get_casualties_by_affiliation():
    """Killed counts broken down by civilian vs military."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            Affiliation,
            SUM(CasualtyCount) AS Total
        FROM Casualties
        WHERE CasualtyType = 'Killed'
        GROUP BY Affiliation
        ORDER BY Total DESC
    """)
    data = rows_to_dicts(cursor)
    conn.close()
    return jsonify(data)


@app.route("/api/incidents/by-day")
def get_incidents_by_day():
    """Number of incidents and total killed per day — for the timeline chart."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            CONVERT(VARCHAR, i.IncidentDate, 23)    AS IncidentDate,
            COUNT(DISTINCT i.IncidentID)             AS IncidentCount,
            ISNULL(SUM(c.CasualtyCount), 0)          AS TotalKilled
        FROM Incidents i
        LEFT JOIN Casualties c
            ON c.IncidentID = i.IncidentID
            AND c.CasualtyType = 'Killed'
        GROUP BY i.IncidentDate
        ORDER BY i.IncidentDate ASC
    """)
    data = rows_to_dicts(cursor)
    conn.close()
    return jsonify(data)


@app.route("/api/named-casualties")
def get_named_casualties():
    """Known named individuals."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            FullName,
            Age,
            Gender,
            Affiliation,
            Nationality,
            CasualtyType,
            VerificationStatus,
            CONVERT(VARCHAR, IncidentDate, 23) AS IncidentDate,
            Location,
            Notes
        FROM vw_NamedCasualties
        ORDER BY IncidentDate DESC
    """)
    data = rows_to_dicts(cursor)
    conn.close()
    return jsonify(data)


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
