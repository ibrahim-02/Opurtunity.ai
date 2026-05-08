"""
Workday scraper — discovery + scraping phases.

Discovery:
  Reads company names from the sec_companies table, generates slug candidates,
  probes all 5 wd-server variants concurrently, extracts career_site from
  redirect URL, validates the jobs API, stores valid boards in workday_companies.

Scraping:
  For each active company in workday_companies, paginates the jobs API,
  applies title + US-location filters, fetches per-job descriptions, and
  inserts via BaseJobRepository (GCS-backed, dedup-safe).

Usage:
    python -m scrapers.workday.main --discover
    python -m scrapers.workday.main --scrape
    python -m scrapers.workday.main --full
    python -m scrapers.workday.main --full --limit 200
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

from loguru import logger
from sqlalchemy import text

import scrapers.workday.settings as _cfg
from database.connection import SessionLocal, init_db, upgrade_schema
from scrapers.filters import is_us_location_multi, passes_title
from scrapers.workday.database.repository import CompanyRepository, JobRepository
from scrapers.workday.scraper.discover import discover_companies
from scrapers.workday.scraper.workday import (
    extract_location,
    fetch_job_description,
    fetch_jobs,
    _job_url,
)

import httpx

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
)
logger.add("logs/workday.log", level="DEBUG", rotation="10 MB", retention="7 days")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_sec_names(session) -> list[str]:
    rows = session.execute(text(f"SELECT company_name FROM {_cfg.SEC_COMPANIES_TABLE}"))
    return [r[0] for r in rows if r[0]]


# ── Discovery ─────────────────────────────────────────────────────────────────

def run_discover(limit: int | None = None):
    logger.info("=== Workday Discovery Phase ===")
    logger.info(
        "Strategy: {} slug candidates × {} wd-server variants probed concurrently",
        3, len(_cfg.WD_NUMS),
    )
    session = SessionLocal()
    company_repo = CompanyRepository(session)

    names = _load_sec_names(session)
    if limit:
        names = names[:limit]

    known_tenants = company_repo.known_tenants()
    logger.info("{} companies loaded | {} already known", len(names), len(known_tenants))

    results = asyncio.run(
        discover_companies(names, concurrency=_cfg.CONCURRENCY, skip_tenants=known_tenants)
    )

    new_count = 0
    for company_name, tenant, wd_num, career_site, job_count in results:
        was_known = tenant in known_tenants
        company_repo.save(company_name, tenant, wd_num, career_site, job_count)
        if not was_known:
            new_count += 1
            logger.info(
                "  + {}: {}.wd{}.myworkdayjobs.com/{} ({} jobs)",
                company_name, tenant, wd_num, career_site, job_count,
            )

    session.close()
    logger.info("=" * 60)
    logger.info("  Found     : {}", len(results))
    logger.info("  New       : {}", new_count)
    logger.info("  Total known: {}", len(known_tenants) + new_count)
    logger.info("=" * 60)


# ── Scrape ────────────────────────────────────────────────────────────────────

def run_scrape(limit: int | None = None, delay: float = _cfg.REQUEST_DELAY):
    logger.info("=== Workday Scrape Phase ===")
    session = SessionLocal()
    company_repo = CompanyRepository(session)
    job_repo = JobRepository(session)

    companies = company_repo.get_active()
    if limit:
        companies = companies[:limit]
    logger.info("Scraping {} active Workday companies...", len(companies))

    totals = {"inserted": 0, "duplicate": 0, "bad_title": 0,
              "non_us": 0, "blocked": 0, "error": 0}

    with httpx.Client(follow_redirects=True) as client:
        for i, company in enumerate(companies, 1):
            tenant = company.tenant
            wd_num = company.wd_num
            career_site = company.career_site
            counts = {k: 0 for k in totals}
            inserted_count = 0

            try:
                offset = 0
                page = 0
                total_jobs = None

                while page < _cfg.MAX_PAGES:
                    try:
                        data = fetch_jobs(tenant, wd_num, career_site, client,
                                          offset=offset, limit=_cfg.JOBS_PER_PAGE)
                    except Exception as e:
                        logger.warning(
                            "  [{}/{}] {} — API error (page {}): {}",
                            i, len(companies), tenant, page, e,
                        )
                        break

                    postings = data.get("jobPostings") or []
                    if total_jobs is None:
                        total_jobs = data.get("total", 0)

                    if not postings:
                        break

                    # Pre-filter titles and locations before fetching descriptions
                    for posting in postings:
                        title = posting.get("title", "")
                        location = extract_location(posting)
                        external_path = posting.get("externalPath", "")

                        if not passes_title(title):
                            counts["bad_title"] += 1
                            continue

                        # Workday may give multiple locations as a comma-separated string
                        loc_parts = [loc.strip() for loc in (location or "").split(",")]
                        if not is_us_location_multi(loc_parts):
                            counts["non_us"] += 1
                            continue

                        link = _job_url(tenant, wd_num, external_path)
                        description = fetch_job_description(
                            tenant, wd_num, career_site, external_path, client
                        )

                        result = job_repo.insert_job(
                            title=title,
                            company_name=company.company_name,
                            description=description,
                            link=link,
                            location=location,
                        )
                        counts[result] = counts.get(result, 0) + 1
                        if result == "inserted":
                            inserted_count += 1

                        time.sleep(delay)

                    offset += len(postings)
                    page += 1
                    if offset >= total_jobs:
                        break

                company_repo.update_scraped(tenant, inserted_count)
                logger.info(
                    "  [{}/{}] {} (wd{}/{}) total={} | "
                    "inserted={} dupes={} bad_title={} non_us={}",
                    i, len(companies), company.company_name, wd_num, career_site,
                    total_jobs or "?",
                    counts["inserted"], counts["duplicate"],
                    counts["bad_title"], counts["non_us"],
                )

            except Exception as e:
                logger.error("  [{}/{}] {} — fatal: {}", i, len(companies), tenant, e)

            for k in counts:
                totals[k] = totals.get(k, 0) + counts[k]

    session.close()
    logger.info("=" * 60)
    logger.info("  Inserted   : {}", totals["inserted"])
    logger.info("  Duplicates : {}", totals["duplicate"])
    logger.info("  Bad title  : {}", totals["bad_title"])
    logger.info("  Non-US     : {}", totals["non_us"])
    logger.info("  Blocked    : {}", totals["blocked"])
    logger.info("  Errors     : {}", totals["error"])
    logger.info("=" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    os.makedirs("logs", exist_ok=True)

    parser = argparse.ArgumentParser(description="Workday scraper")
    parser.add_argument("--discover", action="store_true",
                        help="Probe SEC companies list for Workday boards")
    parser.add_argument("--scrape", action="store_true",
                        help="Scrape jobs from known Workday boards")
    parser.add_argument("--full", action="store_true",
                        help="Discover then scrape")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap number of companies (useful for testing)")
    parser.add_argument("--delay", type=float, default=_cfg.REQUEST_DELAY,
                        help="Seconds between job detail fetches")
    args = parser.parse_args()

    init_db()
    upgrade_schema()

    if args.full:
        run_discover(limit=args.limit)
        run_scrape(limit=args.limit, delay=args.delay)
    elif args.discover:
        run_discover(limit=args.limit)
    elif args.scrape:
        run_scrape(limit=args.limit, delay=args.delay)
    else:
        parser.print_help()
