"""
Lever public API scraper.
Lever exposes all job postings as a public JSON endpoint — no auth, no browser.
API: https://api.lever.co/v0/postings/{slug}?mode=json
"""
import time
from datetime import datetime, timezone

import httpx
from loguru import logger

_API = "https://api.lever.co/v0/postings/{slug}?mode=json&limit=500"


def fetch_jobs(slug: str, client: httpx.Client) -> list[dict]:
    url = _API.format(slug=slug)
    try:
        resp = client.get(url, timeout=15)
        if resp.status_code == 404:
            logger.debug(f"  [{slug}] 404 — slug not found on Lever")
            return []
        resp.raise_for_status()
        data = resp.json()
        if not data:
            logger.debug(f"  [{slug}] 200 but 0 jobs")
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Lever [{slug}] fetch failed: {e}")
        return []


def parse_job(raw: dict, company_name: str) -> dict | None:
    title = raw.get("text", "").strip()
    link  = raw.get("hostedUrl", "").strip()
    if not title or not link:
        return None

    categories = raw.get("categories", {})
    location = categories.get("location") or ""
    if not location:
        all_locs = categories.get("allLocations")
        if isinstance(all_locs, list) and all_locs:
            location = all_locs[0] or ""

    # Build plain-text description from all parts
    parts = []
    if raw.get("descriptionPlain"):
        parts.append(raw["descriptionPlain"].strip())
    for lst in raw.get("lists", []):
        header  = lst.get("text", "")
        content = lst.get("content", "")
        if header:
            parts.append(header)
        if content:
            # strip HTML tags from list content
            import re
            clean = re.sub(r"<[^>]+>", " ", content).strip()
            if clean:
                parts.append(clean)
    if raw.get("additionalPlain"):
        parts.append(raw["additionalPlain"].strip())
    description = "\n\n".join(parts) or None

    # Salary
    sr = raw.get("salaryRange") or {}
    salary = (
        {"min": sr.get("min"), "max": sr.get("max"), "currency": sr.get("currency", "USD")}
        if sr.get("min") or sr.get("max") else None
    )

    posted_date = None
    if raw.get("createdAt"):
        try:
            posted_date = datetime.fromtimestamp(raw["createdAt"] / 1000, tz=timezone.utc)
        except Exception:
            pass

    return {
        "title":        title,
        "company_name": company_name,
        "description":  description,
        "link":         link,
        "location":     location or None,
        "posted_date":  posted_date,
        "salary":       salary,
        "source":       "lever",
    }


def scrape_company(slug: str, company_name: str, client: httpx.Client) -> list[dict]:
    raw_jobs = fetch_jobs(slug, client)
    if not raw_jobs:
        return []
    parsed = []
    for raw in raw_jobs:
        job = parse_job(raw, company_name)
        if job:
            parsed.append(job)
    logger.info(f"  Lever [{company_name}] → {len(parsed)} jobs")
    return parsed
