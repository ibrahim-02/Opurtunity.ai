"""
Ashby scraper entry point.

Usage:
    python -m scrapers.ashby.main
    python -m scrapers.ashby.main --test --company notion
"""
import argparse
import json
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database.connection import SessionLocal
from scrapers.repository import empty_counts
from scrapers.ashby.repository import JobRepository
from scrapers.ashby.scraper import scrape_company

COMPANIES_FILE = Path(__file__).parent / "companies.json"


def run(companies: list[dict]) -> dict:
    session = SessionLocal()
    repo = JobRepository(session)
    totals = empty_counts()

    for entry in companies:
        name = entry["name"]
        slug = entry["slug"]

        try:
            jobs = scrape_company(slug, name)
        except Exception as e:
            logger.warning("  [error] {} ({}): {}", name, slug, e)
            totals["error"] = totals.get("error", 0) + 1
            continue

        if not jobs:
            logger.info("  [empty] {} — no listings returned (bad slug or no open roles)", name)
            continue

        totals["scraped"] = totals.get("scraped", 0) + len(jobs)
        counts = empty_counts()
        for job in jobs:
            result = repo.insert_job(**job)
            counts[result] = counts.get(result, 0) + 1
            totals[result] = totals.get(result, 0) + 1

        logger.info(
            "  {} → scraped={} inserted={} dup={} bad_title={} non_us={} no_company_ref={} blocked={}",
            name,
            len(jobs),
            counts.get("inserted", 0),
            counts.get("duplicate", 0),
            counts.get("bad_title", 0),
            counts.get("non_us", 0),
            counts.get("no_company_ref", 0),
            counts.get("blocked", 0),
        )

    session.close()
    return totals


def main():
    parser = argparse.ArgumentParser(description="Ashby job scraper")
    parser.add_argument("--test", action="store_true", help="Scrape one company only")
    parser.add_argument("--company", type=str, default=None,
                        help="Company slug to test, e.g. notion")
    args = parser.parse_args()

    companies = json.loads(COMPANIES_FILE.read_text())

    if args.test:
        slug = args.company or companies[0]["slug"]
        companies = [c for c in companies if c["slug"] == slug] or [companies[0]]
        logger.info("Test mode — scraping: {} ({})", companies[0]["name"], companies[0]["slug"])

    logger.info("Starting Ashby scrape ({} companies)", len(companies))
    totals = run(companies)

    logger.info(
        "\n=== Ashby scrape complete ===\n"
        "  scraped={} inserted={} duplicate={} bad_title={} "
        "non_us={} no_company_ref={} blocked={} error={}",
        totals.get("scraped", 0),
        totals.get("inserted", 0),
        totals.get("duplicate", 0),
        totals.get("bad_title", 0),
        totals.get("non_us", 0),
        totals.get("no_company_ref", 0),
        totals.get("blocked", 0),
        totals.get("error", 0),
    )


if __name__ == "__main__":
    main()
