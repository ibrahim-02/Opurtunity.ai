import importlib
import os
import sys
import threading
import time as _time
from pathlib import Path

# Add repo root to sys.path so shared modules (database/, models/, llm/, etc.) are importable
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loguru import logger

from database.connection import init_db, upgrade_schema, SessionLocal
from scrapers.linkedin.database.repository import JobRepository
from scrapers.linkedin.scraper.driver import create_driver
from scrapers.linkedin.scraper.linkedin_scraper import LinkedInScraper
from scrapers.linkedin.scraper.card_parser import parse_card

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add("logs/scraper.log", level="DEBUG", rotation="10 MB", retention="7 days")


def _start_settings_watcher():
    """Watch LinkedIn settings.py for changes and hot-reload on save."""
    import scrapers.linkedin.settings as _cfg_mod
    settings_path = Path(_cfg_mod.__file__).resolve()
    last_mtime = settings_path.stat().st_mtime

    def _watch():
        nonlocal last_mtime
        while True:
            _time.sleep(2)
            try:
                mtime = settings_path.stat().st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime
                    importlib.reload(_cfg_mod)
                    logger.info("settings.py changed — configuration reloaded live.")
            except Exception as e:
                logger.warning(f"Settings watcher error: {e}")

    t = threading.Thread(target=_watch, daemon=True, name="settings-watcher")
    t.start()


def run_pipeline():
    _start_settings_watcher()
    logger.info("=== LinkedIn Job Scraper Pipeline Starting ===")

    logger.info("Initializing database...")
    init_db()
    upgrade_schema()
    session = SessionLocal()
    repo = JobRepository(session)

    import time
    driver = create_driver()

    logger.info("Navigating to LinkedIn login page...")
    driver.get("https://www.linkedin.com/login")
    time.sleep(3)

    print("\n" + "=" * 60)
    print("  LINKEDIN LOGIN REQUIRED")
    print("=" * 60)
    print("  1. Switch to the Chrome window")
    print("  2. Log in with your LinkedIn credentials")
    print("  3. Wait until the LinkedIn feed/home page loads")
    print("  4. Come back here and press ENTER to continue")
    print("=" * 60)
    input("\n>>> Press ENTER after you are logged in... ")

    time.sleep(2)
    current_url = driver.current_url
    if "feed" in current_url or "mynetwork" in current_url or "linkedin.com" in current_url:
        logger.info(f"Login successful! Current page: {current_url}")
    else:
        logger.warning(f"Login may not have worked. Current URL: {current_url}")
        cont = input(">>> Continue anyway? (y/n): ").strip().lower()
        if cont != "y":
            driver.quit()
            return

    # Pre-load existing LinkedIn links so we skip duplicate description fetches
    existing_links = repo.existing_linkedin_links()
    logger.info(f"Loaded {len(existing_links)} existing LinkedIn links — duplicates will be skipped before description fetch.")
    scraper = LinkedInScraper(driver, existing_links=existing_links)

    counts = {"inserted": 0, "duplicate": 0, "blocked": 0, "bad_title": 0, "non_us": 0, "error": 0}
    total_scraped = 0
    kw_counts: dict[str, int] = {
        "scraped": 0, "inserted": 0, "duplicate": 0,
        "blocked": 0, "bad_title": 0, "non_us": 0, "error": 0,
    }

    def process_batch(cards: list[dict]):
        nonlocal total_scraped
        total_scraped += len(cards)
        kw_counts["scraped"] += len(cards)
        for card in cards:
            try:
                job = parse_card(html=card["html"], link=card["link"])
            except Exception as e:
                logger.warning(f"Parse error for {card['link']}: {e}")
                counts["error"] += 1
                kw_counts["error"] += 1
                continue
            job.description = card.get("description")
            job.linkedin_followers = card.get("linkedin_followers")
            job.linkedin_employees = card.get("linkedin_employees")
            result = repo.insert_extracted(job)
            counts[result] = counts.get(result, 0) + 1
            kw_counts[result] = kw_counts.get(result, 0) + 1

    def on_keyword_done(keyword: str, _cards_scraped: int):
        repo.log_keyword_done(keyword, kw_counts.copy())
        for k in kw_counts:
            kw_counts[k] = 0

    try:
        import scrapers.linkedin.settings as _cfg
        logger.info(f"Starting LinkedIn scrape | countries={_cfg.SEARCH_COUNTRIES} | "
                    f"max_applicants={_cfg.MAX_APPLICANTS} | pages_per_term={_cfg.MAX_PAGES_PER_SKILL}")
        scraper.scrape_all_skills(
            process_batch=process_batch,
            on_keyword_done=on_keyword_done,
        )

        logger.info("=" * 50)
        logger.info("=== Pipeline Complete ===")
        logger.info(f"  Cards scraped       : {total_scraped}")
        logger.info(f"  Inserted (new)      : {counts['inserted']}")
        logger.info(f"  Duplicates skipped  : {counts['duplicate']}")
        logger.info(f"  Blocked (company)   : {counts['blocked']}")
        logger.info(f"  Filtered (bad title): {counts['bad_title']}")
        logger.info(f"  Filtered (non-US)   : {counts['non_us']}")
        logger.info(f"  Parse errors        : {counts['error']}")
        logger.info(f"  Total jobs in DB    : {repo.get_job_count()}")
        logger.info("=" * 50)

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
    finally:
        driver.quit()
        session.close()
        logger.info("Cleanup complete.")


def run_test(keyword: str = "Data Analyst", max_jobs: int = 5):
    import time
    import random
    _start_settings_watcher()
    logger.info(f"=== TEST MODE: keyword='{keyword}', max_jobs={max_jobs} ===")

    init_db()
    upgrade_schema()
    session = SessionLocal()
    repo = JobRepository(session)
    driver = create_driver()

    driver.get("https://www.linkedin.com/login")
    time.sleep(3)
    print("\n" + "=" * 60)
    print("  LOG IN TO LINKEDIN, THEN PRESS ENTER")
    print("=" * 60)
    input(">>> Press ENTER after logged in... ")

    existing_links = repo.existing_linkedin_links()
    logger.info(f"Loaded {len(existing_links)} existing LinkedIn links for dedup.")
    scraper = LinkedInScraper(driver, existing_links=existing_links)

    try:
        from scrapers.linkedin.scraper.utils import build_search_url
        url = build_search_url(keyword, start=0)
        cards = scraper._scrape_single_page(keyword, url, page_num=1)

        logger.info(f"\nScraped {len(cards)} cards. Processing first {max_jobs}...\n")
        cards = cards[:max_jobs]

        for i, card in enumerate(cards, 1):
            logger.info(f"─── Job {i}/{len(cards)} ───────────────────────────")
            logger.info(f"Link: {card['link']}")
            try:
                job = parse_card(html=card["html"], link=card["link"])
            except Exception as e:
                logger.warning(f"  Parse error: {e} — skipping")
                continue
            logger.info(f"  Title    : {job.title}")
            logger.info(f"  Company  : {job.company_name}")
            logger.info(f"  Location : {job.location}")
            logger.info(f"  Posted   : {job.posted_date}")
            logger.info(f"  Salary   : {job.salary}")
            job.description = card.get("description")
            job.linkedin_followers = card.get("linkedin_followers")
            job.linkedin_employees = card.get("linkedin_employees")
            logger.info(f"  Description: {len(job.description)} chars" if job.description else "  Description: None")
            logger.info(f"  Followers: {job.linkedin_followers}  Employees: {job.linkedin_employees}")
            result = repo.insert_extracted(job)
            logger.info(f"  DB result: {result}")

        logger.info(f"\nTotal jobs now in DB: {repo.get_job_count()}")

    finally:
        driver.quit()
        session.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LinkedIn Job Scraper")

    parser.add_argument("--test", action="store_true", help="Run test mode (1 page, N jobs)")
    parser.add_argument("--keyword", default="Data Analyst", help="Keyword for test mode")
    parser.add_argument("--max", type=int, default=5, help="Max jobs in test mode")
    parser.add_argument("--countries", type=str, default=None,
                        help='Comma-separated LinkedIn location strings.')
    parser.add_argument("--max-applicants", type=int, default=None,
                        help="Skip jobs with >= this many applicants (0 = disabled).")
    parser.add_argument("--pages", type=int, default=None,
                        help="Max pages per keyword per country.")
    parser.add_argument("--skills", type=str, default=None,
                        help='Comma-separated skills to search. Replaces TARGET_SKILLS.')

    args = parser.parse_args()

    import scrapers.linkedin.settings as _cfg

    if args.countries is not None:
        _cfg.SEARCH_COUNTRIES = (
            [c.strip() for c in args.countries.split(",") if c.strip()]
            if args.countries.strip()
            else [""]
        )
    if args.max_applicants is not None:
        _cfg.MAX_APPLICANTS = args.max_applicants
    if args.pages is not None:
        _cfg.MAX_PAGES_PER_SKILL = args.pages
        _cfg.MAX_RESULTS_PER_SKILL = args.pages * 25
    if args.skills is not None:
        custom = [s.strip() for s in args.skills.split(",") if s.strip()]
        _cfg.TARGET_SKILLS = custom
        _cfg.ALL_SEARCH_TERMS = custom + _cfg.SEARCH_QUERIES

    if args.test:
        run_test(keyword=args.keyword, max_jobs=args.max)
    else:
        run_pipeline()
