"""
Ashby job board scraper — async Playwright with concurrent description fetching.

Two-pass strategy:
  Pass 1: one page load per company — captures all job stubs from GraphQL list.
  Pass 2: fetch ALL descriptions concurrently (CONCURRENCY pages at once).
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CONCURRENCY = 6  # simultaneous description page loads


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)


# ── Pass 1: job list ──────────────────────────────────────────────────────────

async def fetch_job_list(slug: str, browser) -> list[dict]:
    """One page load — intercepts GraphQL list response."""
    captured: list[dict] = []
    page = await browser.new_page()

    async def on_response(response):
        if response.status != 200 or "ashby" not in response.url:
            return
        try:
            body = await response.json()
            data = body.get("data") or {}
            for key in ("jobBoard", "jobBoardWithTeams", "jobPostingList"):
                postings = (data.get(key) or {}).get("jobPostings") or []
                if postings:
                    captured.extend(postings)
                    return
        except Exception:
            pass

    page.on("response", on_response)

    try:
        await page.goto(f"https://jobs.ashbyhq.com/{slug}", timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception as exc:
        logger.debug("List timeout for {}: {}", slug, type(exc).__name__)
    finally:
        await page.close()

    return captured


# ── Pass 2: descriptions (concurrent) ────────────────────────────────────────

async def fetch_one_description(slug: str, job_id: str, browser, sem: asyncio.Semaphore) -> tuple[str, str]:
    """Fetch one job's description, rate-limited by semaphore."""
    async with sem:
        page = await browser.new_page()
        captured_html: list[str] = []

        async def on_response(response):
            if response.status != 200 or "ashby" not in response.url:
                return
            try:
                body = await response.json()
                data = body.get("data") or {}
                for key in ("jobPosting", "jobBoardJobPosting", "jobPostingDetail"):
                    posting = data.get(key) or {}
                    html = posting.get("descriptionHtml") or posting.get("description") or ""
                    if html:
                        captured_html.append(html)
                        return
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(
                f"https://jobs.ashbyhq.com/{slug}/{job_id}",
                timeout=20_000,
                wait_until="domcontentloaded",
            )
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        finally:
            await page.close()

        desc = _strip_html(captured_html[0]) if captured_html else ""
        return job_id, desc


async def fetch_all_descriptions(slug: str, job_stubs: list[dict], browser) -> dict[str, str]:
    """Fetch descriptions for all jobs concurrently."""
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        fetch_one_description(slug, raw.get("id", ""), browser, sem)
        for raw in job_stubs
        if raw.get("id")
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        job_id: desc
        for r in results
        if not isinstance(r, Exception)
        for job_id, desc in [r]
    }


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_job(raw: dict, company_name: str, slug: str, description: str = "") -> dict | None:
    title = (raw.get("title") or "").strip()
    if not title:
        return None

    loc = raw.get("locationName") or raw.get("location") or ""
    if isinstance(loc, dict):
        loc = loc.get("city") or loc.get("name") or ""

    link = (raw.get("externalLink") or raw.get("applyLink") or "").strip()
    if not link:
        link = f"https://jobs.ashbyhq.com/{slug}/{raw.get('id', '')}"

    posted_date = None
    for field in ("publishedAt", "updatedAt", "createdAt"):
        val = raw.get(field)
        if val:
            try:
                posted_date = datetime.fromisoformat(val.replace("Z", "+00:00"))
                break
            except (ValueError, AttributeError):
                pass

    return {
        "title": title,
        "company_name": company_name,
        "description": description or _strip_html(raw.get("descriptionHtml") or ""),
        "link": link,
        "location": str(loc).strip() if loc else None,
        "posted_date": posted_date,
        "salary": None,
    }


# ── Main async entry ──────────────────────────────────────────────────────────

async def scrape_company_async(slug: str, company_name: str, browser) -> list[dict]:
    """Fetch all stubs then all descriptions concurrently. Title filter at insert time."""
    raw_jobs = await fetch_job_list(slug, browser)
    if not raw_jobs:
        return []

    logger.info("  {} — {} listings, fetching descriptions ({} concurrent)…",
                company_name, len(raw_jobs), CONCURRENCY)

    descriptions = await fetch_all_descriptions(slug, raw_jobs, browser)

    jobs = []
    for raw in raw_jobs:
        job_id = raw.get("id", "")
        job = parse_job(raw, company_name, slug, description=descriptions.get(job_id, ""))
        if job:
            jobs.append(job)

    with_desc = sum(1 for j in jobs if j["description"])
    logger.info("  {} — {} jobs, {} with description", company_name, len(jobs), with_desc)
    return jobs


def scrape_company(slug: str, company_name: str) -> list[dict]:
    """Sync wrapper — launches its own event loop + browser."""
    from playwright.async_api import async_playwright

    async def _run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            jobs = await scrape_company_async(slug, company_name, browser)
            await browser.close()
            return jobs

    return asyncio.run(_run())
