import httpx
from bs4 import BeautifulSoup
from loguru import logger

_BASE = "https://boards-api.greenhouse.io/v1/boards"

# Browser-like headers sent with every request.
# Greenhouse returns 403 to plain httpx clients; adding a realistic
# User-Agent + Referer/Origin convinces the API to serve the response.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://boards.greenhouse.io",
}


class BoardPrivateError(Exception):
    """Raised when a board still returns 403 even after browser headers."""


def _headers_for(slug: str) -> dict:
    return {**_HEADERS, "Referer": f"https://boards.greenhouse.io/{slug}"}


def fetch_jobs(slug: str, client: httpx.Client) -> list[dict]:
    """Return all job listings for a company (title, id, location, absolute_url)."""
    r = client.get(f"{_BASE}/{slug}/jobs", headers=_headers_for(slug), timeout=15)
    if r.status_code == 403:
        raise BoardPrivateError(f"Board '{slug}' still 403 after browser headers")
    r.raise_for_status()
    return r.json().get("jobs", [])


def fetch_job_detail(slug: str, job_id: int, client: httpx.Client) -> dict | None:
    """Return full job record including HTML description in 'content' field."""
    try:
        r = client.get(
            f"{_BASE}/{slug}/jobs/{job_id}",
            headers=_headers_for(slug),
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"  Detail fetch failed for job {job_id}: {e}")
    return None


def strip_html(html: str | None) -> str | None:
    """Strip HTML tags and return plain text, or None if empty."""
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
    return text if len(text) > 50 else None


def extract_location(job: dict) -> str | None:
    loc = job.get("location")
    if isinstance(loc, dict):
        return loc.get("name")
    return str(loc) if loc else None
