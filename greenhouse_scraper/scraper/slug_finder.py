import re
import asyncio
import httpx
from loguru import logger

_STRIP_SUFFIXES = re.compile(
    r'\b(corp|corporation|inc|incorporated|llc|ltd|co|company|group|holdings|plc|pty|gmbh|ag|sa|nv|the)\b',
    re.I,
)
_GH_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

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


def derive_slug_candidates(name: str) -> list[str]:
    """Turn a company name into 2–3 Greenhouse slug candidates.

    "AMAZON COM INC" → ["amazon", "amazoncom", "amazon-com"]
    "Scale AI"       → ["scale", "scaleai", "scale-ai"]
    """
    cleaned = _STRIP_SUFFIXES.sub("", name)
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned.lower()).strip()
    words = cleaned.split()
    if not words:
        return []
    candidates = [
        words[0],           # first word only — most common Greenhouse slug pattern
        "".join(words),     # all words joined
        "-".join(words),    # hyphenated
    ]
    return list(dict.fromkeys(candidates))  # dedup, preserve order


async def _validate_slug(slug: str, client: httpx.AsyncClient) -> bool:
    headers = {**_HEADERS, "Referer": f"https://boards.greenhouse.io/{slug}"}
    try:
        r = await client.get(_GH_URL.format(slug=slug), headers=headers, timeout=8)
        # Accept 200 (public) and 403 (board exists but restricted — we'll bypass at scrape time)
        return r.status_code in (200, 403)
    except Exception:
        return False


async def _find_valid_slug(
    company_name: str, client: httpx.AsyncClient, semaphore: asyncio.Semaphore
) -> tuple[str, str] | None:
    async with semaphore:
        for slug in derive_slug_candidates(company_name):
            if await _validate_slug(slug, client):
                logger.debug(f"  Matched: '{company_name}' → '{slug}'")
                return (company_name, slug)
    return None


async def discover_companies(
    company_names: list[str], concurrency: int = 20
) -> list[tuple[str, str]]:
    """Test all names concurrently. Returns list of (company_name, slug) for valid boards."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[tuple[str, str]] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            asyncio.create_task(_find_valid_slug(name, client, semaphore))
            for name in company_names
        ]
        total = len(tasks)
        done = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            done += 1
            if result:
                results.append(result)
            if done % 500 == 0 or done == total:
                logger.info(f"  Discovery: {done}/{total} checked | {len(results)} boards found")

    return results
