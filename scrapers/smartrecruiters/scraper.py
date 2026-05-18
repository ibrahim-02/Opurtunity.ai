"""
SmartRecruiters public API scraper.
SmartRecruiters exposes job postings via a paginated REST API -- no auth required.

Jobs list:   https://api.smartrecruiters.com/v1/companies/{companyId}/postings?limit=100&offset=0
Job detail:  https://api.smartrecruiters.com/v1/companies/{companyId}/postings/{jobId}
Apply URL:   https://jobs.smartrecruiters.com/{companyId}/{jobId}
"""
import re
import time
from datetime import datetime, timezone

import httpx
from loguru import logger

_LIST_API   = "https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
_DETAIL_API = "https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{job_id}"
_APPLY_URL  = "https://jobs.smartrecruiters.com/{company_id}/{job_id}"

_PAGE_SIZE = 100
_RETRY_DELAYS = [1, 2, 4]  # seconds between attempts 1->2, 2->3, 3->4


def _get_with_retry(url: str, client: httpx.Client, params: dict | None = None) -> httpx.Response | None:
    """
    GET with 3-attempt exponential backoff (1s, 2s, 4s).
    Returns the Response on success, None on persistent failure.
    """
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)
        try:
            resp = client.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.debug("  429 -- backing off {}s (attempt {})", wait, attempt)
                time.sleep(wait)
                continue
            return resp
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.debug("  Network error on attempt {}: {}", attempt, e)
            if attempt > len(_RETRY_DELAYS):
                return None
    return None


def fetch_all_jobs(company_id: str, client: httpx.Client) -> list[dict]:
    """
    Fetches all job listing stubs for a company, handling pagination via offset.
    Returns raw listing dicts from content[].
    """
    all_jobs: list[dict] = []
    offset = 0

    while True:
        params = {"limit": _PAGE_SIZE, "offset": offset}
        resp = _get_with_retry(_LIST_API.format(company_id=company_id), client, params=params)

        if resp is None:
            logger.warning("SmartRecruiters [{}] -- request failed after retries", company_id)
            break

        if resp.status_code == 404:
            logger.debug("  [{}] 404 -- company not found or no public listings", company_id)
            break

        if resp.status_code != 200:
            logger.warning("SmartRecruiters [{}] -- unexpected status {}", company_id, resp.status_code)
            break

        try:
            data = resp.json()
        except Exception as e:
            logger.warning("SmartRecruiters [{}] -- JSON parse error: {}", company_id, e)
            break

        page = data.get("content", [])
        if not page:
            break

        all_jobs.extend(page)

        total_found = data.get("totalFound", 0)
        offset += len(page)

        if offset >= total_found or len(page) < _PAGE_SIZE:
            break

        # Polite delay between pagination requests
        time.sleep(0.5)

    return all_jobs


def fetch_job_detail(company_id: str, job_id: str, client: httpx.Client) -> dict | None:
    """Fetch the full job detail including description sections."""
    url = _DETAIL_API.format(company_id=company_id, job_id=job_id)
    resp = _get_with_retry(url, client)
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def _extract_description(detail: dict) -> str | None:
    """
    Build a plain-text description from the SmartRecruiters detail sections.
    Strips HTML tags from each section.
    """
    sections = detail.get("jobAd", {}).get("sections", {})
    parts: list[str] = []
    for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        block = sections.get(key, {})
        title = block.get("title", "")
        text  = block.get("text", "")
        if title:
            parts.append(title.strip())
        if text:
            clean = re.sub(r"<[^>]+>", " ", text)
            clean = re.sub(r"\s+", " ", clean).strip()
            if clean:
                parts.append(clean)
    return "\n\n".join(parts) or None


def _build_location(raw: dict) -> str | None:
    """
    Construct a location string from the listing's location object.
    Prefers city+state for US, falls back to city+country or remote label.
    """
    loc = raw.get("location", {})

    # Remote flag
    if loc.get("remote"):
        city    = loc.get("city", "")
        country = loc.get("country", "")
        if country.upper() in ("US", "USA", "UNITED STATES"):
            return "Remote - US"
        if country:
            return f"Remote - {country}"
        return "Remote"

    city    = (loc.get("city") or "").strip()
    region  = (loc.get("region") or "").strip()       # state/province code
    country = (loc.get("country") or "").strip()

    if city and region:
        return f"{city}, {region}"
    if city and country:
        return f"{city}, {country}"
    if city:
        return city
    if region:
        return region
    return None


def parse_job(raw: dict, detail: dict | None, company_name: str, company_id: str) -> dict | None:
    """
    Combine listing stub + detail into the canonical job dict.
    Returns None if mandatory fields are absent.
    """
    job_id = raw.get("id", "").strip()
    title  = raw.get("name", "").strip()
    if not job_id or not title:
        return None

    link = _APPLY_URL.format(company_id=company_id, job_id=job_id)

    location = _build_location(raw)

    # Posted date
    posted_date = None
    released = raw.get("releasedDate") or (detail or {}).get("releasedDate")
    if released:
        try:
            posted_date = datetime.fromisoformat(released.replace("Z", "+00:00"))
        except Exception:
            pass

    # Description (from detail if available)
    description: str | None = None
    if detail:
        description = _extract_description(detail)

    return {
        "title":        title,
        "company_name": company_name,
        "description":  description,
        "link":         link,
        "location":     location,
        "posted_date":  posted_date,
        "salary":       None,   # SmartRecruiters public API does not expose salary
        "source":       "smartrecruiters",
    }


def scrape_company(
    company_id: str,
    company_name: str,
    client: httpx.Client,
    fetch_details: bool = True,
) -> list[dict]:
    """
    Scrape all jobs for a single company.

    fetch_details=True (default): fetches individual job detail pages for
    full descriptions. Set to False for a faster/lighter run (location and
    title only, no description).
    """
    raw_jobs = fetch_all_jobs(company_id, client)
    if not raw_jobs:
        return []

    parsed: list[dict] = []
    for raw in raw_jobs:
        job_id = raw.get("id", "")
        detail: dict | None = None

        if fetch_details and job_id:
            detail = fetch_job_detail(company_id, job_id, client)
            time.sleep(0.5)  # polite delay between detail requests

        job = parse_job(raw, detail, company_name, company_id)
        if job:
            parsed.append(job)

    logger.info("  SmartRecruiters [{}] -> {} jobs", company_name, len(parsed))
    return parsed
