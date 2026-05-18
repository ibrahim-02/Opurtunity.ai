import argparse
import os
import random
import sys
import time
from pathlib import Path

# Repo root on sys.path so shared modules (database/, models/) are importable
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loguru import logger

import scrapers.indeed.settings as _cfg
from database.connection import SessionLocal, init_db, upgrade_schema
from scrapers.indeed.database.repository import JobRepository
from scrapers.indeed.scraper.indeed_scraper import IndeedScraper

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
)
logger.add("logs/indeed.log", level="DEBUG", rotation="10 MB", retention="7 days")


def run_scrape(
    queries: list[str],
    location: str = _cfg.LOCATION,
    days: int = _cfg.DAYS_BACK,
    max_pages: int = _cfg.MAX_PAGES_PER_QUERY,
    fetch_descriptions: bool = _cfg.FETCH_DESCRIPTIONS,
) -> None:
    init_db()
    upgrade_schema()

    session = SessionLocal()
    repo = JobRepository(session)

    total: dict[str, int] = {
        "scraped": 0, "inserted": 0, "duplicate": 0,
        "blocked": 0, "bad_title": 0, "error": 0,
    }

    with IndeedScraper(headless=False) as scraper:
        for i, query in enumerate(queries, 1):
            logger.info("=" * 60)
            logger.info(
                "[{}/{}] Query: '{}' | location='{}' | days={} | pages={}",
                i, len(queries), query, location, days, max_pages,
            )

            counts: dict[str, int] = {
                "scraped": 0, "inserted": 0, "duplicate": 0,
                "blocked": 0, "bad_title": 0, "error": 0,
            }

            try:
                jobs = scraper.scrape_query(
                    query=query,
                    location=location,
                    days=days,
                    max_pages=max_pages,
                    fetch_descriptions=fetch_descriptions,
                )
                counts["scraped"] = len(jobs)

                for job in jobs:
                    try:
                        result = repo.insert_job(
                            title=job["title"],
                            company_name=job.get("company"),
                            description=job.get("description"),
                            link=job["link"],
                            location=job.get("location"),
                            posted_date=IndeedScraper._parse_posted_date(job.get("posted_text")),
                            salary=IndeedScraper._parse_salary(job.get("salary_text")),
                            source="indeed",
                        )
                        counts[result] = counts.get(result, 0) + 1
                    except Exception as e:
                        logger.error("Insert failed for '{}': {}", job.get("title"), e)
                        counts["error"] += 1

            except Exception as e:
                logger.error("Scrape failed for query '{}': {}", query, e)
                counts["error"] += 1

            repo.log_keyword_done(query, counts)

            for k in total:
                total[k] += counts.get(k, 0)

            if i < len(queries):
                delay = random.uniform(_cfg.MIN_DELAY, _cfg.MAX_DELAY)
                logger.info("Sleeping {:.1f}s before next query...", delay)
                time.sleep(delay)

    session.close()

    logger.info("=" * 60)
    logger.info("=== Indeed Scrape Complete ===")
    logger.info("  Queries run   : {}", len(queries))
    logger.info("  Scraped       : {}", total["scraped"])
    logger.info("  Inserted      : {}", total["inserted"])
    logger.info("  Duplicates    : {}", total["duplicate"])
    logger.info("  Blocked       : {}", total["blocked"])
    logger.info("  Bad title     : {}", total["bad_title"])
    logger.info("  Errors        : {}", total["error"])
    logger.info("  Total in DB   : {}", repo.get_job_count())
    logger.info("=" * 60)


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    parser = argparse.ArgumentParser(description="Indeed Selenium Job Scraper")
    parser.add_argument(
        "--query", type=str, default=None,
        help="Single search query (e.g. 'Data Engineer')",
    )
    parser.add_argument(
        "--queries", type=str, default=None,
        help="Comma-separated queries — overrides config list",
    )
    parser.add_argument(
        "--location", type=str, default=_cfg.LOCATION,
        help=f"Search location (default: {_cfg.LOCATION})",
    )
    parser.add_argument(
        "--days", type=int, default=_cfg.DAYS_BACK,
        help="Days back for date filter: 1=24h, 3=3days, 7=week (default: %(default)s)",
    )
    parser.add_argument(
        "--pages", type=int, default=_cfg.MAX_PAGES_PER_QUERY,
        help="Max result pages per query (default: %(default)s)",
    )
    parser.add_argument(
        "--no-descriptions", action="store_true",
        help="Skip fetching full job descriptions (faster, less data)",
    )
    args = parser.parse_args()

    if args.query:
        queries_to_run = [args.query]
    elif args.queries:
        queries_to_run = [q.strip() for q in args.queries.split(",") if q.strip()]
    else:
        queries_to_run = _cfg.ALL_SEARCH_TERMS

    run_scrape(
        queries=queries_to_run,
        location=args.location,
        days=args.days,
        max_pages=args.pages,
        fetch_descriptions=not args.no_descriptions,
    )
