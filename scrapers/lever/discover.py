"""
Discover valid Lever company slugs by probing the public API concurrently.

Lever exposes job postings at:
    https://api.lever.co/v0/postings/{slug}?mode=json

A 200 response with a JSON list = valid slug. A 404 = not on Lever.
Output is written to scrapers.lever/companies_discovered.json.

Usage (from repo root):
    python -m scrapers.lever.discover
    python -m scrapers.lever.discover --min-jobs 1
    python -m scrapers.lever.discover --workers 30
    python -m scrapers.lever.discover --extra "openai,anthropic,my-company"
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

_API = "https://api.lever.co/v0/postings/{slug}?mode=json"

# Curated list of companies confirmed (or strongly suspected) to be on Lever
# right now. Verified hits from previous discovery runs + likely current users.
# Add new candidates via --extra or --from-yc to expand discovery.
_COMPANY_NAMES = [
    # Confirmed active (>0 jobs in recent probe)
    "veeva", "gopuff", "zoox", "spotify", "mistral", "ro", "outreach",
    "neon", "clari",
    # Known long-running Lever users — likely still active
    "netflix", "lyft", "pinterest", "coursera", "khanacademy",
    "ramp", "mercury", "carta", "klaviyo", "attentive",
    "huggingface", "cohere", "perplexity", "cursor", "replit",
    "supabase", "linear", "vercel", "raycast", "ashby",
    "mixpanel", "segment", "amplitude", "heap",
    "mongodb", "cockroachdb", "elastic", "datastax",
    "datadog", "honeycomb", "grafana",
    "1password", "tailscale", "cloudflare",
    "kraken", "marqeta", "wise",
    "asana", "notion", "miro", "loom", "calendly",
    "intercom", "front", "gong", "salesloft",
    "allbirds", "warbyparker", "hims", "carbonhealth",
    "doordash", "instacart",
    "roblox", "duolingo",
    "anduril", "samsara", "verkada", "axon",
    "rivian", "joby", "skydio",
    "databricks", "scale", "weights-and-biases",
    "navan", "expensify", "flexport",
    "benchling", "medidata", "flatiron", "23andme",
    "twilio",
]


_CORP_SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|llc|ltd|limited|co|company|group|holdings|"
    r"plc|sa|nv|gmbh|ag|kk|spa|pty|trust|fund|partners|lp|llp)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9 \-]")


def _clean_name(name: str) -> str:
    """
    Normalize SEC-style names: 'NVIDIA CORP' → 'nvidia', 'Meta Platforms, Inc.' → 'meta platforms'.
    """
    s = name.lower().strip()
    s = s.replace("&", " and ")
    s = _CORP_SUFFIXES.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)        # drop punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _slug_variations(name: str) -> list[str]:
    """Generate plausible slug variations (deduped, order preserved)."""
    cleaned = _clean_name(name)
    base = cleaned or name.lower().strip()
    first = base.split(" ")[0] if base else ""
    variants = [
        base,
        base.replace(" ", ""),
        base.replace(" ", "-"),
        base.replace("-", ""),
        base.replace("_", "-"),
        first,                          # 'meta' from 'meta platforms'
        base + "inc",
        base + "-inc",
    ]
    # also try without spaces variant of "first two words" combo
    parts = base.split(" ")
    if len(parts) >= 2:
        variants.append("".join(parts[:2]))
        variants.append("-".join(parts[:2]))
    return list(dict.fromkeys(v for v in variants if v and len(v) >= 2))


def probe(slug: str, client: httpx.Client, max_retries: int = 2) -> tuple[str, bool, int]:
    """
    Returns (slug, is_valid, job_count).
    Retries on 429 (rate limit) and transient network errors.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = client.get(_API.format(slug=slug), timeout=10)
            if resp.status_code == 404:
                return slug, False, 0
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.debug("  429 on '{}' — backing off {}s", slug, wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                return slug, False, 0
            data = resp.json()
            if isinstance(data, list):
                return slug, True, len(data)
            return slug, False, 0
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt < max_retries:
                time.sleep(1)
                continue
            return slug, False, 0
        except Exception:
            return slug, False, 0
    return slug, False, 0


def _load_db_names(table: str, column: str, limit: int | None) -> list[str]:
    """Load company names from a Postgres table (e.g. public.sec_companies)."""
    from database.connection import SessionLocal
    from sqlalchemy import text
    sql = f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"
    if limit:
        sql += f" LIMIT {int(limit)}"
    session = SessionLocal()
    try:
        rows = session.execute(text(sql)).fetchall()
    finally:
        session.close()
    return [r[0] for r in rows if r[0]]


_YC_API = "https://yc-oss.github.io/api/companies/all.json"


_YC_BATCH_ORDER = {"Winter": 0, "Spring": 1, "Summer": 2, "Fall": 3}


def _yc_batch_key(batch: str | None) -> tuple[int, int]:
    """Sort key: (year, season-within-year). Used to sort newest-first."""
    if not batch:
        return (0, 0)
    parts = batch.strip().split()
    if len(parts) != 2:
        return (0, 0)
    season, year = parts
    try:
        return (int(year), _YC_BATCH_ORDER.get(season, 0))
    except ValueError:
        return (0, 0)


def _load_yc_names(limit: int | None = None) -> list[str]:
    """
    Fetch the full Y Combinator company list (community-maintained mirror),
    sorted newest-batch first (active startups are far more likely to be on Lever).
    """
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(_YC_API)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.error("YC fetch failed: {}", e)
        return []

    # Newest batches first
    data.sort(key=lambda c: _yc_batch_key(c.get("batch")), reverse=True)

    names: list[str] = []
    for c in data:
        slug = c.get("slug")
        name = c.get("name")
        if slug:
            names.append(slug)
        if name and name.lower() != (slug or "").lower():
            names.append(name)

    if limit:
        names = names[:limit]
    if data:
        logger.info(
            "Loaded {} YC names (newest batch: {}, oldest in slice: {}).",
            len(names),
            data[0].get("batch"),
            (data[limit - 1] if limit else data[-1]).get("batch"),
        )
    return names


def run(
    min_jobs: int = 0,
    workers: int = 20,
    extra: list[str] | None = None,
    from_db: bool = False,
    db_table: str = "public.sec_companies",
    db_column: str = "company_name",
    db_limit: int | None = None,
    from_yc: bool = False,
    yc_limit: int | None = None,
    use_seed: bool = True,
) -> None:
    names: list[str] = list(_COMPANY_NAMES) if use_seed else []
    if extra:
        names.extend(extra)
    if from_db:
        db_names = _load_db_names(db_table, db_column, db_limit)
        logger.info("Loaded {} names from {}", len(db_names), db_table)
        names.extend(db_names)
    if from_yc:
        yc_names = _load_yc_names(limit=yc_limit)
        names.extend(yc_names)

    seen: set[str] = set()
    candidates: list[str] = []
    for n in names:
        for s in _slug_variations(n):
            if s not in seen:
                seen.add(s)
                candidates.append(s)

    logger.info("Probing {} unique slug variations across {} workers...",
                len(candidates), workers)

    found: list[dict] = []
    checked = 0
    with httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible; LeverDiscover/1.0)"},
        follow_redirects=True,
    ) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(probe, slug, client): slug for slug in candidates}
            for fut in as_completed(futures):
                checked += 1
                slug, valid, count = fut.result()
                if valid:
                    found.append({
                        "name": slug.replace("-", " ").title(),
                        "slug": slug,
                        "jobs": count,
                    })
                    logger.info("  [{:>4}/{:>4}] OK   {} → {} jobs",
                                checked, len(candidates), slug, count)
                elif checked % 50 == 0:
                    logger.info("  [{:>4}/{:>4}] ... ({} found so far)",
                                checked, len(candidates), len(found))

    found = [c for c in found if c["jobs"] >= min_jobs]
    found.sort(key=lambda x: x["jobs"], reverse=True)

    out = Path(__file__).parent / "companies_discovered.json"
    out.write_text(json.dumps(found, indent=2))

    logger.info("=" * 60)
    logger.info("Probed {} slugs, found {} valid ({} with >= {} jobs).",
                len(candidates), len(found), len(found), min_jobs)
    logger.info("Saved → {}", out)
    logger.info("Top results:")
    for c in found[:25]:
        logger.info("  {:<30s} {:>4} jobs", c["slug"], c["jobs"])
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-jobs", type=int, default=0,
                        help="Only keep companies with >= this many jobs")
    parser.add_argument("--workers", type=int, default=20,
                        help="Concurrent HTTP workers")
    parser.add_argument("--extra", type=str, default="",
                        help="Comma-separated extra company names to probe")
    parser.add_argument("--from-db", action="store_true",
                        help="Load company names from a Postgres table (default: public.sec_companies)")
    parser.add_argument("--db-table", type=str, default="public.sec_companies")
    parser.add_argument("--db-column", type=str, default="company_name")
    parser.add_argument("--db-limit", type=int, default=None,
                        help="Limit DB rows (useful for testing)")
    parser.add_argument("--from-yc", action="store_true",
                        help="Fetch the full Y Combinator company list and probe each one")
    parser.add_argument("--yc-limit", type=int, default=None,
                        help="Limit YC companies (useful for testing)")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip the curated seed list, only probe DB / YC / extra names")
    args = parser.parse_args()

    extra = [s.strip() for s in args.extra.split(",") if s.strip()]
    run(
        min_jobs=args.min_jobs,
        workers=args.workers,
        extra=extra or None,
        from_db=args.from_db,
        db_table=args.db_table,
        db_column=args.db_column,
        db_limit=args.db_limit,
        from_yc=args.from_yc,
        yc_limit=args.yc_limit,
        use_seed=not args.no_seed,
    )
