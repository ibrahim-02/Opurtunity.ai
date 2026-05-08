"""
Quick smoke test for the Workday scraper — no DB, no GCS.

Tests:
  1. Known companies: confirm we can hit the jobs API and get postings
  2. Discovery: run the slug-finder against a small hand-picked name list
  3. Job detail: fetch one description and print the first 300 chars

Run from repo root:
    python -m scrapers.workday.test_workday
"""
import asyncio
import sys
from pathlib import Path

import httpx
from loguru import logger

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

# ── 1. Known boards ──────────────────────────────────────────────────────────
# (tenant, wd_num, career_site)
KNOWN_BOARDS = [
    ("salesforce",   1, "External_Careers"),
    ("adobe",        1, "external_experienced"),
    ("servicenow",   1, "External"),
    ("cisco",        5, "Cisco"),
    ("oracle",       1, "DatabaseSearch"),
    ("workday",      1, "Workday"),
    ("nvidia",       1, "NVIDIAExternalCareerSite"),
    ("amazon",       1, "amazon_jobs"),      # Amazon also uses Workday for some teams
]

def test_known_boards():
    logger.info("=" * 60)
    logger.info("TEST 1 — Known Workday boards")
    logger.info("=" * 60)
    results = []
    with httpx.Client(follow_redirects=True, timeout=10) as client:
        for tenant, wd_num, career_site in KNOWN_BOARDS:
            url = (f"https://{tenant}.wd{wd_num}.myworkdayjobs.com"
                   f"/wday/cxs/{tenant}/{career_site}/jobs")
            try:
                r = client.post(url, json={
                    "appliedFacets": {}, "limit": 3, "offset": 0, "searchText": ""
                }, headers={"Content-Type": "application/json"})
                if r.status_code == 200:
                    data = r.json()
                    total = data.get("total", 0)
                    first = data["jobPostings"][0]["title"] if data.get("jobPostings") else "—"
                    logger.info("  OK  {}.wd{} / {} → {} total | sample: '{}'",
                                tenant, wd_num, career_site, total, first)
                    results.append((tenant, wd_num, career_site, total))
                else:
                    logger.warning("  FAIL {}.wd{} / {} → HTTP {}", tenant, wd_num, career_site, r.status_code)
            except Exception as e:
                logger.warning("  ERR  {}.wd{} / {} → {}", tenant, wd_num, career_site, e)
    return results


# ── 2. Discovery against small name list ─────────────────────────────────────
DISCOVER_NAMES = [
    "Salesforce Inc",
    "Adobe Inc",
    "ServiceNow Inc",
    "Cisco Systems Inc",
    "Oracle Corporation",
    "Workday Inc",
    "NVIDIA Corporation",
    "Snowflake Inc",
    "Datadog Inc",
    "Palantir Technologies",
    "Cloudflare Inc",
    "Twilio Inc",
    "HashiCorp Inc",
    "Databricks",
    "Confluent Inc",
    "MongoDB Inc",
    "Elastic NV",
    "CrowdStrike Holdings",
    "Zscaler Inc",
    "UiPath Inc",
]

async def test_discovery():
    from scrapers.workday.scraper.discover import discover_companies
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST 2 — Discovery against {} known tech names", len(DISCOVER_NAMES))
    logger.info("=" * 60)
    results = await discover_companies(DISCOVER_NAMES, concurrency=10)
    logger.info("")
    logger.info("Discovery results ({} found):", len(results))
    for company_name, tenant, wd_num, career_site, job_count in results:
        logger.info("  {} → {}.wd{} / {} ({} jobs)",
                    company_name, tenant, wd_num, career_site, job_count)
    return results


# ── 3. Job detail fetch ───────────────────────────────────────────────────────
def test_job_detail(boards: list):
    from scrapers.workday.scraper.workday import fetch_jobs, fetch_job_description, _job_url
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST 3 — Job detail fetch (first matching job from each board)")
    logger.info("=" * 60)
    with httpx.Client(follow_redirects=True, timeout=10) as client:
        for tenant, wd_num, career_site, total in boards[:3]:
            try:
                data = fetch_jobs(tenant, wd_num, career_site, client)
                postings = data.get("jobPostings") or []
                if not postings:
                    logger.info("  {} — no postings returned", tenant)
                    continue
                posting = postings[0]
                ext_path = posting.get("externalPath", "")
                link = _job_url(tenant, wd_num, ext_path)
                desc = fetch_job_description(tenant, wd_num, career_site, ext_path, client)
                logger.info("  {} — '{}' @ {}",
                            tenant, posting.get("title"), posting.get("locationsText"))
                logger.info("    link : {}", link)
                if desc:
                    logger.info("    desc : {}...", desc[:200].replace("\n", " "))
                else:
                    logger.info("    desc : (not fetched or empty)")
            except Exception as e:
                logger.warning("  {} — detail error: {}", tenant, e)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test 1 — known boards
    working_boards = test_known_boards()

    # Test 2 — discovery
    discovered = asyncio.run(test_discovery())

    # Test 3 — job detail using the working boards from test 1
    if working_boards:
        test_job_detail(working_boards)
    elif discovered:
        boards_from_discovery = [
            (t, w, c, j) for _, t, w, c, j in discovered
        ]
        test_job_detail(boards_from_discovery)

    logger.info("")
    logger.info("Done. {} known boards reachable, {} discovered from name list.",
                len(working_boards), len(discovered))
