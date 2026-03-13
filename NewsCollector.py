"""
Fetches recent Iran-conflict news via NewsAPI, extracts structured
incident/casualty data using Google Gemini Flash (free tier), and
upserts it into the IranConflictTracker SQL Server database.

Requirements:
    pip install pyodbc google-generativeai requests python-dotenv

Free API keys:
    Gemini  → https://aistudio.google.com  (free, no credit card)
    NewsAPI → https://newsapi.org           (free tier: 100 req/day)

.env file (place in same directory as this script):
    GEMINI_API_KEY=your-gemini-key-here
    NEWSAPI_KEY=your-newsapi-key-here

Usage:
    python update_iran_conflict_db.py               # normal run
    python update_iran_conflict_db.py --dry-run     # preview, no DB writes
    python update_iran_conflict_db.py --days 3      # look back N days (default: 1)
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyodbc
import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Configuration stuff

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NEWSAPI_KEY    = os.getenv("NEWSAPI_KEY")

# SQL Server
SQL_SERVER   = os.getenv("SQL_SERVER")
SQL_DATABASE = os.getenv("SQL_DATABASE")
SQL_USERNAME = os.getenv("SQL_USERNAME")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SQL_SERVER};"
    f"DATABASE={SQL_DATABASE};"
    f"UID={SQL_USERNAME};"
    f"PWD={SQL_PASSWORD};"
)

# NewsAPI settings
NEWSAPI_URL  = "https://newsapi.org/v2/everything"
SEARCH_QUERY = (
    "(Iran attack OR Iran strike OR Iran conflict OR Iran war OR Iran missile) "
    "AND (casualties OR killed OR wounded OR dead OR strikes)"
)
NEWS_LANGUAGE  = "en"
NEWS_SORT_BY   = "publishedAt"
NEWS_PAGE_SIZE = 20   # max articles per run

# Gemini settings
GEMINI_MODEL   = "gemini-2.5-flash"
MIN_CONFIDENCE = 0.7                  # skip extractions below this score, needs to be trustworthy enough

# Logging — writes to both console and a log file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("iran_conflict_updater.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# NewsAPI integration:

def fetch_articles(days_back: int = 1) -> list[dict]:
    """Fetch recent Iran-conflict articles from NewsAPI."""
    if not NEWSAPI_KEY:
        raise EnvironmentError(
            "NEWSAPI_KEY not set. Add it to your .env file.\n"
            "Get a free key at: https://newsapi.org"
        )

    from_date = (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "q":        SEARCH_QUERY,
        "from":     from_date,
        "language": NEWS_LANGUAGE,
        "sortBy":   NEWS_SORT_BY,
        "pageSize": NEWS_PAGE_SIZE,
        "apiKey":   NEWSAPI_KEY,
    }

    log.info(f"Fetching news articles (last {days_back} day(s))…")
    resp = requests.get(NEWSAPI_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    articles = data.get("articles", [])
    log.info(f"  → {len(articles)} article(s) retrieved")
    return articles


def articles_to_text(articles: list[dict]) -> str:
    """Combine article snippets into a single text block for Gemini."""
    parts = []
    for i, a in enumerate(articles, 1):
        title       = a.get("title", "").strip()
        source      = a.get("source", {}).get("name", "Unknown")
        published   = a.get("publishedAt", "")[:10]        # YYYY-MM-DD
        description = (a.get("description") or "").strip()
        content     = (a.get("content")     or "").strip()
        body        = description if description else content
        parts.append(
            f"[Article {i}] {published} | {source}\n"
            f"Title: {title}\n"
            f"Body:  {body}\n"
        )
    return "\n---\n".join(parts)


# Gemini AI API integration:

EXTRACTION_PROMPT = """
You are a precise military/conflict data analyst. Extract structured incident
and casualty data from the news articles below about the Iran conflict that
began in late February 2026.

Return ONLY a valid JSON object — no markdown fences, no commentary, nothing else.

JSON schema to follow exactly:
{
  "incidents": [
    {
      "incident_key":      "SHORT_UNIQUE_KEY_YYYYMMDD",
      "incident_date":     "YYYY-MM-DD",
      "location_city":     "City name",
      "location_region":   "Province/state or null",
      "location_country":  "Country",
      "incident_type":     "Airstrike|Missile Strike|Drone Strike|Naval Attack|Ground Attack|Other",
      "attacking_party":   "United States|Israel|Iran|Hezbollah|Kataib Hezbollah|Popular Mobilisation Forces|Unknown/Multiple",
      "target_type":       "Civilian|Military|Infrastructure|Leadership|Mixed",
      "description":       "One-sentence factual summary",
      "reported_by":       "Source names, comma-separated",
      "confidence":        0.0,
      "casualties": [
        {
          "full_name":      "Full name or Unknown",
          "age":            null,
          "gender":         "Male|Female|null",
          "affiliation":    "Civilian|Military|Paramilitary|Government/Leadership",
          "nationality":    "Country name or Unknown/Multiple",
          "casualty_type":  "Killed|Wounded|Missing",
          "casualty_count": 1,
          "is_aggregate":   false,
          "verification":   "Verified|Reported|Unverified|Disputed",
          "reported_by":    "Source",
          "notes":          "Extra context or null"
        }
      ]
    }
  ]
}

Rules:
- Keep description and notes fields brief (under 100 characters each).
- Only include incidents that are NEW and clearly dated within the last few days.
- Set confidence (0.0–1.0) to reflect how certain you are this is a real new incident.
  Low confidence = vague, contradictory, or unverifiable reports.
- For vague casualty counts (e.g. "several", "dozens"), set is_aggregate=true,
  use a conservative integer, and set verification="Unverified".
- incident_key must be UPPERCASE_SNAKE_CASE, e.g. DAMASCUS_STRIKE_0306
- Return {"incidents": []} if nothing new and credible is found.

Articles:
"""


def extract_incidents(articles_text: str) -> list[dict]:
    """Send articles to Gemini Flash and parse structured incident data."""
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY not set. Add it to your .env file.\n"
            "Get a free key at: https://aistudio.google.com"
        )

    client = genai.Client(api_key=GEMINI_API_KEY)

    full_prompt = EXTRACTION_PROMPT + articles_text

    log.info("Sending articles to Gemini Flash for extraction…")
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,    # low temperature = more deterministic, fewer hallucinations
            max_output_tokens=8192,
        ),
    )

    raw = response.text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    # Also strip a trailing fence if present
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"Gemini returned invalid JSON: {e}\nRaw output:\n{raw[:500]}")
        return []

    incidents = data.get("incidents", [])
    log.info(f"  → Gemini extracted {len(incidents)} candidate incident(s)")
    return incidents


# Database Helpers and connections:

def get_connection() -> pyodbc.Connection:
    try:
        return pyodbc.connect(CONN_STR)
    except pyodbc.Error as e:
        log.error(
            f"Could not connect to SQL Server.\n"
            f"  Server:   {SQL_SERVER}\n"
            f"  Database: {SQL_DATABASE}\n"
            f"  Error:    {e}\n"
            f"  Tip: Check SQL_SERVER in the script matches your instance name.\n"
            f"       Run 'SELECT @@SERVERNAME' in SSMS to confirm."
        )
        raise


def get_or_create_location(cursor, city: str, region: Optional[str], country: str) -> int:
    """Return LocationID for the given city/country, inserting a new row if needed."""
    city = city or "Unknown"
    country = country or "Unknown"

    location_key = (
        f"{city}_{country}".upper()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(",", "")
        [:100]
    )

    cursor.execute(
        "SELECT LocationID FROM Locations WHERE LocationKey = ?",
        location_key,
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    # New location — insert it
    # REPLACE with this:
    cursor.execute(
        """
        INSERT INTO Locations (LocationKey, City, Region, Country, LocationType)
            OUTPUT INSERTED.LocationID
        VALUES (?, ?, ?, ?, 'Unknown')
        """,
        location_key, city, region, country,
    )
    new_id = int(cursor.fetchone()[0])

    log.info(f"  New location inserted: {city}, {country} (LocationID={new_id})")
    return new_id


def get_party_id(cursor, party_name: str) -> Optional[int]:
    """Look up PartyID by exact name; return None if not found."""
    if not party_name:
        return None
    cursor.execute(
        "SELECT PartyID FROM Parties WHERE PartyName = ?",
        party_name,
    )
    row = cursor.fetchone()
    return row[0] if row else None


def incident_exists(cursor, incident_key: str) -> bool:
    """Check whether an incident with this key is already in the DB."""
    cursor.execute(
        "SELECT 1 FROM Incidents WHERE IncidentKey = ?",
        incident_key,
    )
    return cursor.fetchone() is not None


def insert_incident(
    cursor,
    inc: dict,
    location_id: int,
    attacking_party_id: Optional[int],
) -> int:
    """Insert one incident row and return its new IncidentID."""
    # REPLACE the entire INSERT in insert_incident with:
    cursor.execute(
        """
        INSERT INTO Incidents
        (IncidentKey, IncidentDate, LocationID, IncidentType,
         AttackingPartyID, TargetType, Description, ReportedBy,
         VerifiedByUSCENTCOM)
            OUTPUT INSERTED.IncidentID
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        inc["incident_key"],
        inc["incident_date"],
        location_id,
        inc.get("incident_type", "Other"),
        attacking_party_id,
        inc.get("target_type"),
        inc.get("description"),
        inc.get("reported_by"),
    )
    return int(cursor.fetchone()[0])

def insert_casualty(
    cursor,
    cas: dict,
    incident_id: int,
    nationality_party_id: Optional[int],
) -> None:
    """Insert one casualty row."""
    cursor.execute(
        """
        INSERT INTO Casualties
            (FullName, Age, Gender, Affiliation, NationalityPartyID,
             IncidentID, CasualtyType, CasualtyCount, IsAggregate,
             VerificationStatus, ReportedBy, Notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        cas.get("full_name", "Unknown"),
        cas.get("age"),
        cas.get("gender"),
        cas.get("affiliation", "Unknown"),
        nationality_party_id,
        incident_id,
        cas.get("casualty_type", "Killed"),
        cas.get("casualty_count", 1),
        1 if cas.get("is_aggregate") else 0,
        cas.get("verification", "Unverified"),
        cas.get("reported_by"),
        cas.get("notes"),
    )


# ── Main upsert logic ──────────────────────────────────────────────────────────

def process_incidents(incidents: list[dict], dry_run: bool = False) -> None:
    """Validate, filter by confidence, and upsert incidents into SQL Server."""
    if not incidents:
        log.info("No incidents to process.")
        return

    inserted_count = 0
    skipped_count  = 0
    casualty_count = 0

    conn   = get_connection() if not dry_run else None
    cursor = conn.cursor()    if not dry_run else None

    for inc in incidents:
        key        = inc.get("incident_key", "").strip()
        confidence = float(inc.get("confidence", 0))
        date_str   = inc.get("incident_date", "").strip()

        # Confidence filter: log warning and skip
        if confidence < MIN_CONFIDENCE:
            log.warning(
                f"SKIP  [{key or '?'}]  confidence {confidence:.2f} < {MIN_CONFIDENCE}  "
                f"— {inc.get('description', '')[:80]}"
            )
            skipped_count += 1
            continue

        # Required field validation
        if not key:
            log.warning(f"SKIP  Incident has no incident_key — {inc.get('description', '')[:60]}")
            skipped_count += 1
            continue

        if not date_str:
            log.warning(f"SKIP  [{key}]  missing incident_date")
            skipped_count += 1
            continue

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            log.warning(f"SKIP  [{key}]  invalid date format '{date_str}' (expected YYYY-MM-DD)")
            skipped_count += 1
            continue

        # Dry-run: print what would be inserted
        if dry_run:
            log.info(
                f"DRY-RUN  [{key}]  {date_str}  conf={confidence:.2f}  "
                f"{inc.get('location_city')}, {inc.get('location_country')}  "
                f"— {inc.get('description', '')[:80]}"
            )
            for cas in inc.get("casualties", []):
                log.info(
                    f"           casualty: {cas.get('casualty_count')}x "
                    f"{cas.get('casualty_type')} ({cas.get('affiliation')}) "
                    f"— {cas.get('full_name')}"
                )
            inserted_count += 1
            continue

        # Duplicate check
        if incident_exists(cursor, key):
            log.info(f"EXISTS [{key}]  already in database — skipping")
            skipped_count += 1
            continue

        # Resolve foreign keys
        location_id = get_or_create_location(
            cursor,
            inc.get("location_city") or "Unknown",
            inc.get("location_region"),
            inc.get("location_country") or "Unknown",
        )

        attacking_party_id = get_party_id(cursor, inc.get("attacking_party", ""))
        if not attacking_party_id:
            attacking_party_id = get_party_id(cursor, "Unknown/Multiple")

        # Insert incident
        try:
            incident_id = insert_incident(cursor, inc, location_id, attacking_party_id)
        except pyodbc.Error as e:
            log.error(f"FAIL  [{key}]  error inserting incident: {e}")
            conn.rollback()
            skipped_count += 1
            continue

        # Insert casualties (all-or-nothing per incident)
        cas_list = inc.get("casualties", [])
        fail = False
        for cas in cas_list:
            nat_party_id = get_party_id(cursor, cas.get("nationality", ""))
            if not nat_party_id:
                nat_party_id = get_party_id(cursor, "Unknown/Multiple")
            try:
                insert_casualty(cursor, cas, incident_id, nat_party_id)
                casualty_count += 1
            except pyodbc.Error as e:
                log.error(f"FAIL  [{key}]  error inserting casualty '{cas.get('full_name')}': {e}")
                conn.rollback()
                fail = True
                break

        if not fail:
            conn.commit()
            log.info(
                f"INSERT [{key}]  {date_str}  conf={confidence:.2f}  "
                f"{inc.get('location_city')}, {inc.get('location_country')}  "
                f"({len(cas_list)} casualty row(s))"
            )
            inserted_count += 1
        else:
            skipped_count += 1

    if conn:
        conn.close()

    log.info("─" * 60)
    log.info(
        f"Done.  "
        f"Inserted: {inserted_count}  |  "
        f"Skipped/warned: {skipped_count}  |  "
        f"Casualty rows added: {casualty_count}"
    )


# Entry point

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update IranConflictTracker DB using NewsAPI + Gemini Flash (free)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview extractions without writing anything to the database",
    )
    parser.add_argument(
        "--days", type=int, default=1,
        help="How many days back to search for articles (default: 1)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        log.info("=== DRY RUN MODE — no data will be written to the database ===")

    log.info(f"=== Iran Conflict DB Updater  {datetime.now():%Y-%m-%d %H:%M} ===")

    # Fetch articles from NewsAPI
    try:
        articles = fetch_articles(days_back=args.days)
    except Exception as e:
        log.error(f"Failed to fetch articles: {e}")
        sys.exit(1)

    if not articles:
        log.info("No articles returned for the time period. Nothing to do.")
        sys.exit(0)

    # Extract structured incident data via Gemini Flash
    articles_text = articles_to_text(articles)
    try:
        incidents = extract_incidents(articles_text)
    except Exception as e:
        log.error(f"Gemini extraction failed: {e}")
        sys.exit(1)

    # Upsert new incidents and casualties into SQL Server
    process_incidents(incidents, dry_run=args.dry_run)


if __name__ == "__main__":
    main()