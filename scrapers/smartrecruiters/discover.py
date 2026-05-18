"""
Discover valid SmartRecruiters company IDs by probing the public API concurrently.

SmartRecruiters exposes job postings at:
    https://api.smartrecruiters.com/v1/companies/{companyId}/postings?limit=1&offset=0

A 200 response with a JSON object containing a `content` list = valid company.
A 404 = not on SmartRecruiters (or no public listings).
Output is written to scrapers/smartrecruiters/companies_discovered.json.

Usage (from repo root):
    python -m scrapers.smartrecruiters.discover
    python -m scrapers.smartrecruiters.discover --min-jobs 1
    python -m scrapers.smartrecruiters.discover --workers 30
    python -m scrapers.smartrecruiters.discover --extra "shopify,stripe,my-company"
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

_API = "https://api.smartrecruiters.com/v1/companies/{company_id}/postings?limit=1&offset=0"

# Curated list of companies confirmed (or strongly suspected) to use SmartRecruiters.
# SmartRecruiters is popular with large enterprises, especially European multinationals.
_COMPANY_NAMES = [
    # German / European multinationals
    "bosch", "visa", "aldi", "lidl", "samsungelectronics", "ikea",
    "bmw", "continental", "schaeffler", "bayer", "basf", "henkel",
    "siemens", "allianz", "munichre", "dhl", "lufthansa",
    "deutsche-telekom", "adidas", "puma", "zalando", "hellofresh",
    "delivery-hero", "about-you", "auto1-group", "trivago",
    # HR / SaaS
    "personio", "celonis", "contentful", "sumup",
    # Additional known users
    "mcdonald's", "mcdonalds", "hilton", "marriott", "hyatt",
    "bosch-group", "continental-ag", "volkswagen", "audi",
    "mercedes-benz", "mercedesbenz", "porsche", "zf",
    "rhenus", "db-schenker", "dbschenker", "kuehne-nagel", "kuehnenegnal",
    "evonik", "lanxess", "covestro", "wacker", "clariant",
    "fresenius", "merck", "roche", "novartis", "astrazeneca",
    "philips", "asml", "dsm", "akzonobel",
    "inditex", "zara", "mango", "desigual",
    "carrefour", "auchan", "leclerc",
    "orange", "swisscom", "vodafone",
    "airbus", "thales", "safran", "rolls-royce",
    "shell", "totalenergies", "bp", "eni",
    "abb", "atlas-copco", "sandvik", "volvo",
    "loreal", "lvmh", "kering", "hermes",
    "nestle", "danone", "unilever", "heineken", "ab-inbev",
    "societe-generale", "bnpparibas", "unicredit", "intesa-sanpaolo",
    "generali", "mapfre", "axa",
    "capgemini", "atos", "sopra-steria", "dxc-technology",
    "nttdata", "infosys", "wipro", "hcltech",
    "accenture", "ibm", "oracle", "sap", "salesforce",
]


_CORP_SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|llc|ltd|limited|co|company|group|holdings|"
    r"plc|sa|nv|gmbh|ag|kk|spa|pty|trust|fund|partners|lp|llp)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9 \-]")


def _clean_name(name: str) -> str:
    """
    Normalize names: 'BOSCH GMBH' → 'bosch', 'Bayer AG' → 'bayer'.
    """
    s = name.lower().strip()
    s = s.replace("&", " and ")
    s = _CORP_SUFFIXES.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _slug_variations(name: str) -> list[str]:
    """Generate plausible company ID variations (deduped, order preserved)."""
    cleaned = _clean_name(name)
    base = cleaned or name.lower().strip()
    first = base.split(" ")[0] if base else ""
    variants = [
        base,
        base.replace(" ", ""),
        base.replace(" ", "-"),
        base.replace("-", ""),
        base.replace("_", "-"),
        first,
        base + "inc",
        base + "-inc",
    ]
    parts = base.split(" ")
    if len(parts) >= 2:
        variants.append("".join(parts[:2]))
        variants.append("-".join(parts[:2]))
    return list(dict.fromkeys(v for v in variants if v and len(v) >= 2))


def probe(company_id: str, client: httpx.Client, max_retries: int = 2) -> tuple[str, bool, int]:
    """
    Returns (company_id, is_valid, job_count).
    Retries on 429 (rate limit) and transient network errors.
    """
    url = _API.format(company_id=company_id)
    for attempt in range(max_retries + 1):
        try:
            resp = client.get(url, timeout=10)
            if resp.status_code == 404:
                return company_id, False, 0
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.debug("  429 on '{}' — backing off {}s", company_id, wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                return company_id, False, 0
            data = resp.json()
            if isinstance(data, dict) and "content" in data:
                total = data.get("totalFound", len(data["content"]))
                return company_id, True, total
            return company_id, False, 0
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt < max_retries:
                time.sleep(1)
                continue
            return company_id, False, 0
        except Exception:
            return company_id, False, 0
    return company_id, False, 0


def run(
    min_jobs: int = 0,
    workers: int = 20,
    extra: list[str] | None = None,
    use_seed: bool = True,
) -> None:
    names: list[str] = list(_COMPANY_NAMES) if use_seed else []
    if extra:
        names.extend(extra)

    seen: set[str] = set()
    candidates: list[str] = []
    for n in names:
        for s in _slug_variations(n):
            if s not in seen:
                seen.add(s)
                candidates.append(s)

    logger.info("Probing {} unique company ID variations across {} workers...",
                len(candidates), workers)

    found: list[dict] = []
    checked = 0
    with httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible; SmartRecruitersDiscover/1.0)"},
        follow_redirects=True,
    ) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(probe, cid, client): cid for cid in candidates}
            for fut in as_completed(futures):
                checked += 1
                company_id, valid, count = fut.result()
                if valid:
                    found.append({
                        "name": company_id.replace("-", " ").title(),
                        "company_id": company_id,
                        "jobs": count,
                    })
                    logger.info("  [{:>4}/{:>4}] OK   {} → {} jobs",
                                checked, len(candidates), company_id, count)
                elif checked % 50 == 0:
                    logger.info("  [{:>4}/{:>4}] ... ({} found so far)",
                                checked, len(candidates), len(found))

    found = [c for c in found if c["jobs"] >= min_jobs]
    found.sort(key=lambda x: x["jobs"], reverse=True)

    out = Path(__file__).parent / "companies_discovered.json"
    out.write_text(json.dumps(found, indent=2))

    logger.info("=" * 60)
    logger.info("Probed {} company IDs, found {} valid ({} with >= {} jobs).",
                len(candidates), len(found), len(found), min_jobs)
    logger.info("Saved → {}", out)
    logger.info("Top results:")
    for c in found[:25]:
        logger.info("  {:<35s} {:>4} jobs", c["company_id"], c["jobs"])
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-jobs", type=int, default=0,
                        help="Only keep companies with >= this many jobs")
    parser.add_argument("--workers", type=int, default=20,
                        help="Concurrent HTTP workers")
    parser.add_argument("--extra", type=str, default="",
                        help="Comma-separated extra company IDs to probe")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip the curated seed list, only probe extra names")
    args = parser.parse_args()

    extra = [s.strip() for s in args.extra.split(",") if s.strip()]
    run(
        min_jobs=args.min_jobs,
        workers=args.workers,
        extra=extra or None,
        use_seed=not args.no_seed,
    )
