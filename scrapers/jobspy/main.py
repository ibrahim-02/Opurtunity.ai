"""
JobSpy scraper — scrapes Indeed, Glassdoor, ZipRecruiter via jobspy library.
No browser needed. Results go into the same jobsql table.

Usage (from repo root):
    python -m scrapers.jobspy.main
    python -m scrapers.jobspy.main --sites indeed
    python -m scrapers.jobspy.main --hours 24 --results 30
"""
import argparse
import json
import sys
import time
from pathlib import Path

from loguru import logger
from sqlalchemy import text

from database.connection import SessionLocal

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

_CONFIG_FILE = Path(__file__).parent / "config.json"


def load_config() -> dict:
    return json.loads(_CONFIG_FILE.read_text())


def _safe_salary(row) -> dict | None:
    try:
        mn = float(row.get("min_amount")) if row.get("min_amount") else None
        mx = float(row.get("max_amount")) if row.get("max_amount") else None
        if mn or mx:
            return {"min": mn, "max": mx, "currency": row.get("currency", "USD")}
    except Exception:
        pass
    return None


def _title_relevant(title: str, term: str) -> bool:
    """Return True if the job title actually matches the search phrase."""
    if not term or not title:
        return True
    t = title.lower()
    phrase = term.lower().strip()
    if phrase in t:
        return True
    # Accept if all individual words appear as whole words (catches "Data Engineering")
    import re
    words = phrase.split()
    return all(re.search(rf"\b{re.escape(w)}", t) for w in words)


def upsert_jobs(session, rows, term: str = "") -> tuple[int, int, int]:
    inserted = dupes = skipped = 0
    for _, row in rows.iterrows():
        link = str(row.get("job_url", "")).strip()
        if not link:
            continue

        existing = session.execute(
            text("SELECT id FROM jobsql WHERE link = :link"), {"link": link}
        ).fetchone()
        if existing:
            dupes += 1
            continue

        title   = str(row.get("title", "")).strip() or None
        company = str(row.get("company", "")).strip() or None
        if not title:
            continue

        if not _title_relevant(title, term):
            logger.debug(f"  ✗ skipped (off-topic): {title}")
            skipped += 1
            continue

        description = str(row.get("description", "")).strip() or None
        location    = str(row.get("location", "")).strip() or None
        source      = str(row.get("site", "indeed")).lower()

        posted_date = None
        if row.get("date_posted") is not None:
            try:
                import pandas as pd
                pd_date = pd.to_datetime(row["date_posted"], utc=True)
                posted_date = pd_date.to_pydatetime()
            except Exception:
                pass

        salary = _safe_salary(row)

        session.execute(text("""
            INSERT INTO jobsql (title, company_name, description, link, location,
                                posted_date, salary, source)
            VALUES (:title, :company_name, :description, :link, :location,
                    :posted_date, :salary, :source)
        """), {
            "title":        title,
            "company_name": company,
            "description":  description,
            "link":         link,
            "location":     location,
            "posted_date":  posted_date,
            "salary":       json.dumps(salary) if salary else None,
            "source":       source,
        })
        logger.info(f"  ✓ [{source}] {title} @ {company or '?'} → {link}")
        inserted += 1

    session.commit()
    return inserted, dupes, skipped


def run(sites: list[str] | None, hours_old: int, results_per_search: int,
        term_override: str | None = None, location_override: str = "United States"):
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("jobspy not installed — run: pip install python-jobspy")
        return

    config  = load_config()
    sites   = sites or config["sites"]
    session = SessionLocal()
    totals  = {"inserted": 0, "dupes": 0, "errors": 0}

    searches = (
        [{"term": term_override, "location": location_override}]
        if term_override
        else config["searches"]
    )
    logger.info(f"Running {len(searches)} searches across {sites}...")

    for i, s in enumerate(searches, 1):
        term     = s["term"]
        location = s["location"]
        logger.info(f"[{i}/{len(searches)}] '{term}' in {location}")
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=term,
                location=location,
                results_wanted=results_per_search,
                hours_old=hours_old,
                country_indeed=config.get("country", "USA"),
                verbose=0,
            )
            if df is None or df.empty:
                logger.info(f"  → 0 results")
                continue

            ins, dup, skip = upsert_jobs(session, df, term=term)
            totals["inserted"] += ins
            totals["dupes"]    += dup
            logger.info(f"  → {ins} inserted, {dup} dupes, {skip} off-topic skipped")
        except Exception as e:
            totals["errors"] += 1
            logger.warning(f"  Search failed: {e}")

        time.sleep(2)

    session.close()
    logger.info("=" * 50)
    logger.info(f"  Inserted : {totals['inserted']}")
    logger.info(f"  Dupes    : {totals['dupes']}")
    logger.info(f"  Errors   : {totals['errors']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JobSpy multi-source scraper")
    parser.add_argument("--sites",    nargs="+", default=None,
                        help="Sites: indeed glassdoor zip_recruiter")
    parser.add_argument("--hours",    type=int, default=72,
                        help="Max age of jobs in hours (default: 72)")
    parser.add_argument("--results",  type=int, default=50,
                        help="Results per search term (default: 50)")
    parser.add_argument("--term",     type=str, default=None,
                        help="Single search term override e.g. 'data engineer'")
    parser.add_argument("--location", type=str, default="United States",
                        help="Location for --term search (default: United States)")
    args = parser.parse_args()
    run(
        sites=args.sites,
        hours_old=args.hours,
        results_per_search=args.results,
        term_override=args.term,
        location_override=args.location,
    )
