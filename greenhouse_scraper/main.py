import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Add repo root to sys.path so shared modules (database/, models/, llm/, etc.) are importable
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
from loguru import logger

import greenhouse_scraper.config.settings as _cfg
from database.connection import init_db, upgrade_schema, SessionLocal
from greenhouse_scraper.database.repository import JobRepository, CompanyRepository
from greenhouse_scraper.scraper.slug_finder import discover_companies
from greenhouse_scraper.scraper.greenhouse import (
    fetch_jobs, fetch_job_detail, strip_html, extract_location, BoardPrivateError,
)

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
)
logger.add("logs/greenhouse.log", level="DEBUG", rotation="10 MB", retention="7 days")


def _load_company_names() -> list[str]:
    from sqlalchemy import text
    session = SessionLocal()
    try:
        rows = session.execute(text(f"SELECT company_name FROM {_cfg.SEC_COMPANIES_TABLE}"))
        return [r[0] for r in rows if r[0]]
    finally:
        session.close()


def run_discover(limit: int | None = None):
    logger.info("=== Discovery Phase: finding companies with Greenhouse boards ===")
    names = _load_company_names()
    if limit:
        names = names[:limit]
    logger.info(f"Testing {len(names)} company names with {_cfg.CONCURRENCY} concurrent workers...")

    results = asyncio.run(discover_companies(names, concurrency=_cfg.CONCURRENCY))
    logger.info(f"Found {len(results)} companies with Greenhouse boards")

    session = SessionLocal()
    repo = CompanyRepository(session)
    new_count = 0
    for company_name, slug in results:
        existing = repo.get_company_count()
        repo.save_discovered(company_name, slug)
        if repo.get_company_count() > existing:
            new_count += 1
    session.close()
    logger.info(f"Discovery complete — {new_count} new companies saved to greenhouse_companies table")


def _all_location_strings(job: dict) -> list[str]:
    """Collect every location string Greenhouse exposes on a job listing."""
    locs = []
    primary = extract_location(job)
    if primary:
        locs.append(primary)
    for office in job.get("offices", []):
        if isinstance(office, dict):
            if office.get("location"):
                locs.append(office["location"])
            if office.get("name"):
                locs.append(office["name"])
    return locs


def _is_usa_job(job: dict) -> bool:
    locations = _all_location_strings(job)
    if not locations:
        return False
    combined = " | ".join(locations).lower()
    return any(term in combined for term in _cfg.USA_LOCATION_TERMS)


def run_scrape(limit: int | None = None):
    logger.info("=== Scrape Phase: fetching jobs from Greenhouse boards ===")
    session = SessionLocal()
    company_repo = CompanyRepository(session)
    job_repo = JobRepository(session)

    companies = company_repo.get_active_companies()
    if limit:
        companies = companies[:limit]
    logger.info(f"Scraping {len(companies)} companies...")

    counts = {"inserted": 0, "duplicate": 0, "bad_title": 0, "error": 0}

    with httpx.Client(follow_redirects=True) as client:
        for i, company in enumerate(companies, 1):
            try:
                jobs = fetch_jobs(company.slug, client)
                title_matched = [
                    j for j in jobs
                    if any(kw in j.get("title", "").lower() for kw in _cfg.TITLE_KEYWORDS)
                    and not any(ex in j.get("title", "").lower() for ex in _cfg.TITLE_EXCLUDE_KEYWORDS)
                ]
                matching = [j for j in title_matched if _is_usa_job(j)]
                logger.info(
                    f"  [{i}/{len(companies)}] {company.company_name} ({company.slug}): "
                    f"{len(jobs)} total | {len(title_matched)} title-matched | {len(matching)} usa-filtered"
                )

                inserted_this_company = 0
                for job in matching:
                    try:
                        detail = fetch_job_detail(company.slug, job["id"], client)
                        description = strip_html(detail.get("content") if detail else None)
                        result = job_repo.insert_job(
                            company_name=company.company_name,
                            title=job["title"],
                            description=description,
                            link=job.get(
                                "absolute_url",
                                f"https://boards.greenhouse.io/{company.slug}/jobs/{job['id']}",
                            ),
                            location=extract_location(job),
                            source="greenhouse",
                        )
                        counts[result] += 1
                        if result == "inserted":
                            inserted_this_company += 1
                        time.sleep(_cfg.REQUEST_DELAY)
                    except Exception as e:
                        logger.warning(f"    Job error (id={job.get('id')}): {e}")
                        counts["error"] += 1

                company_repo.update_scraped(company.slug, inserted_this_company)
                time.sleep(_cfg.REQUEST_DELAY)

            except BoardPrivateError:
                logger.warning(
                    f"  [{i}/{len(companies)}] {company.slug}: 403 — skipping this run"
                )
            except Exception as e:
                logger.warning(f"  Company error for '{company.slug}': {e}")
                counts["error"] += 1

    session.close()
    logger.info("=" * 50)
    logger.info("=== Scrape Complete ===")
    logger.info(f"  Inserted      : {counts['inserted']}")
    logger.info(f"  Duplicates    : {counts['duplicate']}")
    logger.info(f"  Bad title     : {counts['bad_title']}")
    logger.info(f"  Errors        : {counts['error']}")
    logger.info(f"  Total in DB   : {job_repo.get_job_count()}")
    logger.info("=" * 50)


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    parser = argparse.ArgumentParser(description="Greenhouse Job Scraper")
    parser.add_argument("--discover", action="store_true",
                        help="Find which companies use Greenhouse (~30 min for all 8K)")
    parser.add_argument("--scrape", action="store_true",
                        help="Scrape jobs from known Greenhouse companies")
    parser.add_argument("--full", action="store_true",
                        help="Run discovery then scraping")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap number of companies processed (useful for testing)")
    args = parser.parse_args()

    init_db()
    upgrade_schema()

    if args.full:
        run_discover(limit=args.limit)
        run_scrape(limit=args.limit)
    elif args.discover:
        run_discover(limit=args.limit)
    elif args.scrape:
        run_scrape(limit=args.limit)
    else:
        parser.print_help()
