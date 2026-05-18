"""
Fast probe: check which slugs have active Ashby job boards.
Uses async Playwright — intercepts only the GraphQL job-list response (no descriptions).

Usage:
    python -m scrapers.ashby.probe              # check all companies.json, update in place
    python -m scrapers.ashby.probe --dry-run    # print results only, no write
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from loguru import logger
from playwright.async_api import async_playwright

COMPANIES_FILE = Path(__file__).parent / "companies.json"
CONCURRENCY = 6
PAGE_TIMEOUT   = 20_000   # ms for page.goto
RESPONSE_WAIT  = 12.0     # seconds to wait for GraphQL response after page load

# Only intercept actual Ashby API calls, not CDN assets
API_HOSTS = ("api.ashbyhq.com", "app.ashbyhq.com")


async def probe_slug(slug: str, browser, sem: asyncio.Semaphore) -> tuple[str, int]:
    """Returns (slug, job_count). 0 means no public board or board is empty."""
    async with sem:
        page = await browser.new_page()
        job_count = 0
        got_result = asyncio.Event()

        async def on_response(response):
            nonlocal job_count
            if got_result.is_set():
                return
            if response.status != 200:
                return
            if not any(h in response.url for h in API_HOSTS):
                return
            try:
                body = await response.json()
                data = body.get("data") or {}
                for key in ("jobBoard", "jobBoardWithTeams", "jobPostingList"):
                    postings = (data.get(key) or {}).get("jobPostings") or []
                    if postings:
                        job_count = len(postings)
                        break
                got_result.set()
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(
                f"https://jobs.ashbyhq.com/{slug}",
                timeout=PAGE_TIMEOUT,
                wait_until="domcontentloaded",
            )
            # Wait explicitly for GraphQL response (don't rely on networkidle)
            try:
                await asyncio.wait_for(got_result.wait(), timeout=RESPONSE_WAIT)
            except asyncio.TimeoutError:
                pass
        except Exception:
            pass
        finally:
            await page.close()

        return slug, job_count


async def probe_all(companies: list[dict]) -> list[tuple[str, str, int]]:
    sem = asyncio.Semaphore(CONCURRENCY)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        tasks = [probe_slug(c["slug"], browser, sem) for c in companies]

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()

    slug_to_name = {c["slug"]: c["name"] for c in companies}
    results = []
    for r in results_raw:
        if isinstance(r, Exception):
            continue
        slug, count = r
        results.append((slug, slug_to_name.get(slug, slug), count))
    return results


def main():
    parser = argparse.ArgumentParser(description="Probe Ashby job board slugs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results only — do not update companies.json")
    args = parser.parse_args()

    companies = json.loads(COMPANIES_FILE.read_text())
    if not companies:
        logger.error("companies.json is empty — run discover first")
        sys.exit(1)

    logger.info("Probing {} companies ({} concurrent)…", len(companies), CONCURRENCY)
    results = asyncio.run(probe_all(companies))
    results.sort(key=lambda x: (-x[2], x[1]))

    active = [(s, n, c) for s, n, c in results if c > 0]
    empty  = [(s, n, c) for s, n, c in results if c == 0]

    logger.info("\n✓ Active job boards ({}):", len(active))
    for slug, name, count in active:
        logger.info("  {:35s} {:30s} {:>4} jobs", slug, name, count)

    logger.info("\n✗ No board / empty ({}):", len(empty))
    for slug, name, _ in empty:
        logger.info("  {} ({})", slug, name)

    if args.dry_run:
        logger.info("\nDry-run — companies.json not changed")
        return

    active_companies = [
        {"name": name, "slug": slug}
        for slug, name, _ in sorted(active, key=lambda x: x[1].lower())
    ]
    COMPANIES_FILE.write_text(json.dumps(active_companies, indent=2, ensure_ascii=False))
    logger.info("companies.json updated — {} active companies kept", len(active_companies))


if __name__ == "__main__":
    main()
