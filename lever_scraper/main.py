"""
Lever scraper — fetches jobs from companies using Lever ATS.

Usage (from repo root):
    python -m lever_scraper.main
    python -m lever_scraper.main --limit 10
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from loguru import logger
from sqlalchemy import text

from database.connection import SessionLocal
from lever_scraper.scraper import scrape_company

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

_COMPANIES_FILE = Path(__file__).parent / "companies.json"


def load_companies() -> list[dict]:
    return json.loads(_COMPANIES_FILE.read_text())


def upsert_jobs(session, jobs: list[dict]) -> tuple[int, int]:
    inserted = dupes = 0
    for job in jobs:
        existing = session.execute(
            text("SELECT id FROM jobsql WHERE link = :link"),
            {"link": job["link"]},
        ).fetchone()
        if existing:
            dupes += 1
            continue
        session.execute(text("""
            INSERT INTO jobsql (title, company_name, description, link, location,
                                posted_date, salary, source)
            VALUES (:title, :company_name, :description, :link, :location,
                    :posted_date, :salary, :source)
        """), {
            **job,
            "salary": json.dumps(job["salary"]) if job["salary"] else None,
        })
        inserted += 1
    session.commit()
    return inserted, dupes


def run(limit: int | None = None):
    companies = load_companies()
    if limit:
        companies = companies[:limit]

    logger.info(f"Scraping {len(companies)} Lever companies...")
    session = SessionLocal()
    totals = {"inserted": 0, "dupes": 0, "empty": 0}

    with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as client:
        for i, company in enumerate(companies, 1):
            slug = company["slug"]
            name = company["name"]
            logger.info(f"[{i}/{len(companies)}] {name}")

            jobs = scrape_company(slug, name, client)
            if not jobs:
                totals["empty"] += 1
                continue

            ins, dup = upsert_jobs(session, jobs)
            totals["inserted"] += ins
            totals["dupes"]    += dup
            time.sleep(0.5)

    session.close()
    logger.info("=" * 50)
    logger.info(f"  Inserted : {totals['inserted']}")
    logger.info(f"  Dupes    : {totals['dupes']}")
    logger.info(f"  No jobs  : {totals['empty']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max companies to process")
    args = parser.parse_args()
    run(limit=args.limit)
