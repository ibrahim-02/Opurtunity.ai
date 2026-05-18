"""
SmartRecruiters scraper -- fetches jobs from companies using SmartRecruiters ATS.

All filtering (USA-only, title allowlist, company blocklist) and GCS upload
is delegated to scrapers.repository.BaseJobRepository -- single source of truth
shared with LinkedIn / Indeed / Greenhouse / Lever.

Usage (from repo root):
    python -m scrapers.smartrecruiters.main
    python -m scrapers.smartrecruiters.main --limit 10
    python -m scrapers.smartrecruiters.main --no-details
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from loguru import logger

from database.connection import SessionLocal
from scrapers.smartrecruiters.repository import JobRepository
from scrapers.smartrecruiters.scraper import scrape_company

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

_COMPANIES_FILE = Path(__file__).parent / "companies.json"


def load_companies() -> list[dict]:
    return json.loads(_COMPANIES_FILE.read_text())


def run(limit: int | None = None, fetch_details: bool = True):
    companies = load_companies()
    if limit:
        companies = companies[:limit]

    logger.info(
        "Scraping {} SmartRecruiters companies (USA-only, role-filtered, GCS-backed, details={})...",
        len(companies), fetch_details,
    )
    session = SessionLocal()
    repo = JobRepository(session)
    existing = repo.existing_links()
    logger.info(
        "Loaded {} existing SmartRecruiters links -- duplicates will skip immediately.",
        len(existing),
    )

    totals = {
        "inserted": 0, "duplicate": 0, "non_us": 0,
        "bad_title": 0, "blocked": 0, "no_company_ref": 0,
        "error": 0, "empty": 0,
    }

    with httpx.Client(
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
    ) as client:
        for i, company in enumerate(companies, 1):
            company_id   = company["company_id"]
            company_name = company["name"]
            logger.info("[{}/{}] {}", i, len(companies), company_name)

            jobs = scrape_company(company_id, company_name, client, fetch_details=fetch_details)
            if not jobs:
                totals["empty"] += 1
                continue

            counts = {
                "inserted": 0, "duplicate": 0, "non_us": 0,
                "bad_title": 0, "blocked": 0, "no_company_ref": 0, "error": 0,
            }
            for job in jobs:
                # Quick in-memory dedup before insert_job touches the DB
                if job["link"] in existing:
                    counts["duplicate"] += 1
                    continue
                result = repo.insert_job(
                    title=job["title"],
                    company_name=job["company_name"],
                    description=job.get("description"),
                    link=job["link"],
                    location=job.get("location"),
                    posted_date=job.get("posted_date"),
                    salary=job.get("salary"),
                )
                counts[result] = counts.get(result, 0) + 1
                if result == "inserted":
                    existing.add(job["link"])

            for k in counts:
                totals[k] = totals.get(k, 0) + counts[k]
            logger.info(
                "  -> inserted={} dupes={} non_us={} bad_title={} blocked={} no_ref={}",
                counts["inserted"], counts["duplicate"], counts["non_us"],
                counts["bad_title"], counts["blocked"], counts["no_company_ref"],
            )
            time.sleep(0.5)

    session.close()
    logger.info("=" * 60)
    logger.info("  Inserted   : {}", totals["inserted"])
    logger.info("  Duplicates : {}", totals["duplicate"])
    logger.info("  Non-US     : {}", totals["non_us"])
    logger.info("  Bad title  : {}", totals["bad_title"])
    logger.info("  Blocked    : {}", totals["blocked"])
    logger.info("  No company ref: {}", totals["no_company_ref"])
    logger.info("  No jobs    : {}", totals["empty"])
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max companies to process")
    parser.add_argument(
        "--no-details", action="store_true",
        help="Skip per-job detail fetches (faster but no descriptions)",
    )
    args = parser.parse_args()
    run(limit=args.limit, fetch_details=not args.no_details)
