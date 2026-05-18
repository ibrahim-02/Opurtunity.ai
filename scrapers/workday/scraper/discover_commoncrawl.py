"""
Discover Workday job boards via Common Crawl CDX index.

Common Crawl has indexed millions of pages including Workday job boards.
We query their CDX API for all URLs under *.myworkdayjobs.com — this gives
exact (tenant, wd_num, career_site) tuples with zero slug guessing.

Each result is validated against the live Workday jobs API before saving.
"""
import asyncio
import json
import re
from collections import defaultdict

import httpx
from loguru import logger

import scrapers.workday.settings as _cfg
from scrapers.workday.scraper.discover import _validate

COLLINFO_URL  = "https://index.commoncrawl.org/collinfo.json"
CDX_TEMPLATE  = (
    "https://index.commoncrawl.org/{index}"
    "?url=*.myworkdayjobs.com&matchType=domain"
    "&output=json&fl=url&limit=200000"
)

# Captures: tenant, wd_num (digit), career_site
_URL_RE = re.compile(
    r"https?://([a-z0-9-]+)\.wd(\d)\.myworkdayjobs\.com/(?:wday/cxs/[^/]+/)?([^/?#\s]+)",
    re.IGNORECASE,
)
_SKIP_PATHS = {"job", "jobs", "apply", "search", "wday", "cxs", "en-us", "en_us"}


# ── CDX fetching ─────────────────────────────────────────────────────────────

async def _get_latest_indices(client: httpx.AsyncClient, n: int = 3) -> list[str]:
    """Return IDs of the N most recent Common Crawl indices."""
    try:
        r = await client.get(COLLINFO_URL, timeout=20.0)
        r.raise_for_status()
        data = r.json()
        return [entry["id"] for entry in data[:n]]
    except Exception as exc:
        logger.warning("Could not fetch CC index list: {}", exc)
        # Hard-code a recent fallback so the script still runs
        return ["CC-MAIN-2025-13", "CC-MAIN-2025-08", "CC-MAIN-2024-51"]


async def _fetch_cdx(index_id: str, client: httpx.AsyncClient) -> list[str]:
    """Stream CDX response and return all URLs found."""
    url = CDX_TEMPLATE.format(index=index_id)
    urls: list[str] = []
    try:
        async with client.stream("GET", url, timeout=120.0) as r:
            if r.status_code != 200:
                logger.warning("CDX {} → HTTP {}", index_id, r.status_code)
                return []
            async for line in r.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    u = obj.get("url") or ""
                    if u:
                        urls.append(u)
                except (json.JSONDecodeError, AttributeError):
                    pass
        logger.info("  {} → {} URLs", index_id, len(urls))
    except Exception as exc:
        logger.warning("CDX fetch error for {}: {}", index_id, exc)
    return urls


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_url(url: str) -> tuple[str, int, str] | None:
    """Extract (tenant, wd_num, career_site) from a myworkdayjobs.com URL."""
    m = _URL_RE.search(url)
    if not m:
        return None
    tenant     = m.group(1).lower()
    wd_num     = int(m.group(2))
    career_site = m.group(3)
    if career_site.lower() in _SKIP_PATHS:
        return None
    return tenant, wd_num, career_site


def _extract_boards(urls: list[str]) -> dict[tuple[str, int], str]:
    """
    Return {(tenant, wd_num): career_site} — one career_site per board.
    When multiple career_sites appear for the same board, pick the most frequent.
    """
    freq: dict[tuple[str, int], defaultdict] = {}
    for url in urls:
        parsed = _parse_url(url)
        if not parsed:
            continue
        tenant, wd_num, career_site = parsed
        key = (tenant, wd_num)
        if key not in freq:
            freq[key] = defaultdict(int)
        freq[key][career_site] += 1

    return {
        key: max(cs_counts, key=cs_counts.get)
        for key, cs_counts in freq.items()
    }


# ── Validation ────────────────────────────────────────────────────────────────

async def _validate_board(
    tenant: str,
    wd_num: int,
    career_site: str,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple[str, int, str, int] | None:
    """Returns (tenant, wd_num, career_site, job_count) or None if invalid."""
    async with sem:
        count = await _validate(tenant, wd_num, career_site, client)
        if count >= 0:
            return tenant, wd_num, career_site, count
        return None


# ── Public entry point ────────────────────────────────────────────────────────

async def discover_from_commoncrawl(
    num_indices: int = 3,
    concurrency: int = 30,
    skip_tenants: set[str] | None = None,
) -> list[tuple[str, int, str, int]]:
    """
    Query Common Crawl and return validated Workday boards.

    Returns list of (tenant, wd_num, career_site, job_count).
    Uses `skip_tenants` to avoid re-validating already known boards.
    """
    skip_tenants = skip_tenants or set()

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=_cfg._HEADERS,
    ) as client:
        indices = await _get_latest_indices(client, num_indices)
        logger.info("Querying {} Common Crawl indices: {}", len(indices), indices)

        # Collect all URLs from all indices
        all_urls: list[str] = []
        for idx in indices:
            urls = await _fetch_cdx(idx, client)
            all_urls.extend(urls)

        logger.info("Total URLs collected: {}", len(all_urls))

        # Parse to unique (tenant, wd_num) → career_site mapping
        boards = _extract_boards(all_urls)
        new_boards = {k: v for k, v in boards.items() if k[0] not in skip_tenants}
        logger.info(
            "Unique boards from CC: {} | {} already known | {} to validate",
            len(boards), len(boards) - len(new_boards), len(new_boards),
        )

        # Validate each board against live API
        sem = asyncio.Semaphore(concurrency)
        tasks = [
            _validate_board(tenant, wd_num, career_site, client, sem)
            for (tenant, wd_num), career_site in new_boards.items()
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

    results = [r for r in raw if isinstance(r, tuple)]
    logger.info("Validated {} live Workday boards from Common Crawl", len(results))
    return results
