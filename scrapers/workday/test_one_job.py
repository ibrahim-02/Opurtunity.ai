"""
Brute-force Workday discovery test.

Pulls company names from the sec_companies table (or a fallback list if DB
is unavailable), runs full discovery against all wd1-5 × career_site patterns,
then fetches ONE job from every board found to confirm the API works end-to-end.

Run from repo root:
    python -m scrapers.workday.test_one_job                  # full SEC list
    python -m scrapers.workday.test_one_job --limit 300      # first 300 companies
    python -m scrapers.workday.test_one_job --no-db          # offline fallback list
"""
import argparse
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

# Fallback list when --no-db is used (well-known Workday users)
_FALLBACK_NAMES = [
    "Salesforce Inc", "Adobe Inc", "ServiceNow Inc", "Cisco Systems Inc",
    "Oracle Corporation", "Workday Inc", "NVIDIA Corporation", "Snowflake Inc",
    "Datadog Inc", "CrowdStrike Holdings", "Palantir Technologies Inc",
    "Cloudflare Inc", "MongoDB Inc", "Elastic NV", "Zscaler Inc",
    "UiPath Inc", "Twilio Inc", "Okta Inc", "Splunk Inc",
    "Palo Alto Networks Inc", "Fortinet Inc", "Veeva Systems Inc",
    "Pegasystems Inc", "NICE Systems", "Ceridian HCM",
    "Cornerstone OnDemand", "Instructure Holdings", "Domo Inc",
    "Zendesk Inc", "Medallia Inc", "Qualtrics International",
    "Box Inc", "Dropbox Inc", "Zoom Video Communications",
    "DocuSign Inc", "Coupa Software", "Procore Technologies",
    "Paylocity Corp", "Paycom Software", "Paychex Inc",
    "ADP Inc", "Automatic Data Processing", "Fiserv Inc",
    "Jack Henry Associates", "Broadridge Financial Solutions",
    "SS&C Technologies", "Black Knight Inc", "NCR Corporation",
    "Nuance Communications", "Open Text Corporation",
    "Manhattan Associates", "Verint Systems", "PROS Holdings",
    "Informatica Inc", "MicroStrategy Inc", "Teradata Corporation",
    "Alteryx Inc", "Thoughtworks Holding", "EPAM Systems",
    "Cognizant Technology Solutions", "Infosys Limited",
    "Wipro Limited", "HCL Technologies", "Tech Mahindra",
    "Accenture PLC", "Capgemini SE", "CGI Inc",
    "Leidos Holdings", "SAIC Inc", "Booz Allen Hamilton",
    "ManTech International", "CACI International", "DXC Technology",
    "Unisys Corporation", "Conduent Inc", "Concentrix Corporation",
    "Gartner Inc", "Forrester Research", "IHS Markit",
    "Verisk Analytics", "TransUnion LLC", "Equifax Inc",
    "Fair Isaac Corporation", "Dun & Bradstreet Holdings",
    "RealPage Inc", "CoStar Group", "Zillow Group",
    "Redfin Corporation", "Opendoor Technologies",
    "Blend Labs Inc", "nCino Inc", "Q2 Holdings",
    "Enova International", "LoanCore Capital", "Blend",
    "Marqeta Inc", "Green Dot Corporation", "WEX Inc",
    "Payoneer Global", "i2c Inc", "Galileo Financial Technologies",
    "Repay Holdings", "Paya Holdings", "Nuvei Corporation",
    "Shift4 Payments", "EVO Payments", "Cass Information Systems",
]


def _load_from_db(limit: int | None) -> list[str]:
    from sqlalchemy import text
    from database.connection import SessionLocal
    session = SessionLocal()
    try:
        rows = session.execute(text("SELECT company_name FROM public.sec_companies"))
        names = [r[0] for r in rows if r[0]]
        if limit:
            names = names[:limit]
        return names
    finally:
        session.close()


def fetch_one_job(tenant: str, wd_num: int, career_site: str) -> dict | None:
    url = (f"https://{tenant}.wd{wd_num}.myworkdayjobs.com"
           f"/wday/cxs/{tenant}/{career_site}/jobs")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    with httpx.Client(follow_redirects=True, timeout=10) as client:
        r = client.post(url, json={
            "appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""
        }, headers=headers)
        r.raise_for_status()
        data = r.json()
        postings = data.get("jobPostings") or []
        return postings[0] if postings else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap number of companies from SEC list")
    parser.add_argument("--no-db", action="store_true",
                        help="Use offline fallback list instead of DB")
    args = parser.parse_args()

    # ── Load company names ────────────────────────────────────────────────────
    if args.no_db:
        names = _FALLBACK_NAMES
        logger.info("Using offline fallback list ({} companies)", len(names))
    else:
        try:
            names = _load_from_db(args.limit)
            logger.info("Loaded {} company names from sec_companies table", len(names))
        except Exception as e:
            logger.warning("DB unavailable ({}), falling back to offline list", e)
            names = _FALLBACK_NAMES
            if args.limit:
                names = names[:args.limit]

    # ── Run brute-force discovery ─────────────────────────────────────────────
    from scrapers.workday.scraper.discover import discover_companies
    logger.info("Starting brute-force Workday discovery...")
    found = asyncio.run(discover_companies(names, concurrency=25))

    if not found:
        logger.warning("No Workday boards found. Check connectivity or try --no-db.")
        return

    logger.info("")
    logger.info("=" * 70)
    logger.info("DISCOVERY COMPLETE — {} Workday boards found", len(found))
    logger.info("=" * 70)

    # ── Fetch one job from each found board ───────────────────────────────────
    ok, empty, fail = 0, 0, 0

    for company_name, tenant, wd_num, career_site, total_jobs in sorted(found, key=lambda x: x[0]):
        try:
            job = fetch_one_job(tenant, wd_num, career_site)
            if job:
                title = (job.get("title") or job.get("jobTitle") or job.get("name") or "?")
                location = (job.get("locationsText") or job.get("locationText") or
                            job.get("location") or "?")
                logger.info(
                    "OK   {:30s} | wd{} | {:25s} | total={:5d} | '{}' — {}",
                    company_name[:30], wd_num, career_site[:25], total_jobs,
                    title[:60], location,
                )
                ok += 1
            else:
                logger.info(
                    "EMPTY {:30s} | wd{} | {:25s} | total={}",
                    company_name[:30], wd_num, career_site[:25], total_jobs,
                )
                empty += 1
        except Exception as e:
            logger.warning("FAIL  {:30s} | wd{} | {} | {}", company_name[:30], wd_num, career_site, e)
            fail += 1

    logger.info("")
    logger.info("One-job test: {} OK  |  {} empty boards  |  {} errors", ok, empty, fail)


if __name__ == "__main__":
    main()
