"""
Workday brute-force discovery — flat semaphore design.

Previous version nested asyncio.gather inside asyncio.gather which spawned
tens of thousands of tasks simultaneously and stalled the event loop.

This version builds a flat list of (name, slug, wd_num) combos and processes
them all through a single semaphore. DNS failures return in <100ms so the
whole 8k SEC list takes ~5-10 minutes.

Strategy per combo:
  1. GET main page, follow redirects, extract career_site from URL.
  2. Validate with POST to jobs API.
  3. If step 1 misses career_site, try 4 common fallback patterns.
"""
import asyncio
import re

import httpx
from loguru import logger

import scrapers.workday.settings as _cfg

_STRIP_SUFFIXES = re.compile(
    r'\b(corp|corporation|inc|incorporated|llc|ltd|co|company|group|holdings|'
    r'plc|pty|gmbh|ag|sa|nv|the|technologies|technology|solutions|services|'
    r'systems|international|global|enterprises|ventures|partners|industries|'
    r'financial|capital|management|investments|bancorp|bank|trust|insurance)\b',
    re.I,
)
_LOCALE_RE = re.compile(r'^/[a-z]{2}[-_][A-Za-z]{2}/', re.I)


def derive_slug_candidates(name: str) -> list[str]:
    cleaned = _STRIP_SUFFIXES.sub("", name)
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned.lower()).strip()
    words = cleaned.split()
    if not words:
        return []
    return list(dict.fromkeys([
        words[0],
        "".join(words),
        "-".join(words),
    ]))


def _extract_career_site(path: str) -> str | None:
    path = _LOCALE_RE.sub("/", path)
    parts = [p for p in path.split("/") if p]
    for part in parts:
        if part.lower() in ("jobs", "job", "search", "apply"):
            continue
        return part
    return None


def _fallback_patterns(slug: str) -> list[str]:
    """4 patterns cover the vast majority of edge cases."""
    return list(dict.fromkeys([
        "External_Careers",
        "External",
        "Careers",
        slug.capitalize(),
        slug,
    ]))


async def _validate(
    tenant: str, wd_num: int, career_site: str, client: httpx.AsyncClient
) -> int:
    """Returns total job count or -1 on failure."""
    url = (f"https://{tenant}.wd{wd_num}.myworkdayjobs.com"
           f"/wday/cxs/{tenant}/{career_site}/jobs")
    try:
        r = await client.post(
            url,
            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
            timeout=_cfg.REQUEST_TIMEOUT,
            headers={**_cfg._HEADERS, "Content-Type": "application/json"},
        )
        if r.status_code == 200:
            data = r.json()
            if "jobPostings" in data:
                return int(data.get("total", 0))
    except Exception:
        pass
    return -1


async def _check_combo(
    company_name: str,
    slug: str,
    wd_num: int,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple[str, str, int, str, int] | None:
    """
    Try one (slug, wd_num). Returns (company_name, tenant, wd_num, career_site, jobs)
    or None.
    """
    async with sem:
        base = f"https://{slug}.wd{wd_num}.myworkdayjobs.com"
        career_site = None

        # Fast path: GET → redirect → extract career_site
        try:
            timeout = httpx.Timeout(
                connect=_cfg.CONNECT_TIMEOUT, read=_cfg.REQUEST_TIMEOUT,
                write=5.0, pool=5.0,
            )
            r = await client.get(
                base, timeout=timeout,
                headers=_cfg._HEADERS, follow_redirects=True,
            )
            if r.status_code == 200:
                career_site = _extract_career_site(str(r.url.path))
        except Exception:
            return None  # domain doesn't exist — skip immediately

        if career_site:
            total = await _validate(slug, wd_num, career_site, client)
            if total >= 0:
                return (company_name, slug, wd_num, career_site, total)

        # Fallback: try a handful of common career_site names
        for cs in _fallback_patterns(slug):
            total = await _validate(slug, wd_num, cs, client)
            if total >= 0:
                return (company_name, slug, wd_num, cs, total)

    return None


async def discover_companies(
    company_names: list[str],
    concurrency: int = _cfg.CONCURRENCY,
    skip_tenants: set[str] | None = None,
) -> list[tuple[str, str, int, str, int]]:
    """
    Returns list of (company_name, tenant, wd_num, career_site, job_count).
    """
    skip_tenants = skip_tenants or set()

    # Build flat list of (name, slug, wd_num) combos — skipping known tenants
    combos: list[tuple[str, str, int]] = []
    skipped = 0
    for name in company_names:
        slugs = derive_slug_candidates(name)
        if any(s in skip_tenants for s in slugs):
            skipped += 1
            continue
        for slug in slugs:
            for wd_num in _cfg.WD_NUMS:
                combos.append((name, slug, wd_num))

    logger.info(
        "Brute-force discovery: {} companies → {} combos | "
        "{} already known (skipped) | concurrency={}",
        len(company_names) - skipped, len(combos), skipped, concurrency,
    )

    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[str, str, int, str, int]] = []
    found_tenants: set[str] = set()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            asyncio.create_task(_check_combo(name, slug, wd_num, client, sem))
            for name, slug, wd_num in combos
        ]
        total = len(tasks)
        done = 0

        for coro in asyncio.as_completed(tasks):
            result = await coro
            done += 1

            if result:
                _, tenant, _, _, _ = result
                # Only keep first match per tenant (ignore duplicate slugs)
                if tenant not in found_tenants:
                    found_tenants.add(tenant)
                    results.append(result)
                    logger.info("  FOUND [{}]: {}", len(results), result[0])

            if done % 500 == 0 or done == total:
                logger.info(
                    "  Progress: {}/{} combos done | {} boards found",
                    done, total, len(results),
                )

    return results
