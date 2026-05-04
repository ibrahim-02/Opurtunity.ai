"""
Discover valid Lever company slugs by probing the public API.
Tries common slug variations for a given company name list.

Usage:
    python -m lever_scraper.discover
    python -m lever_scraper.discover --min-jobs 1
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

_API = "https://api.lever.co/v0/postings/{slug}?mode=json"

# Broad list of company names to probe — script generates slug variations automatically
_COMPANY_NAMES = [
    "netflix", "airbnb", "lyft", "doordash", "instacart", "pinterest",
    "snap", "twitter", "discord", "notion", "figma", "canva", "miro",
    "linear", "vercel", "supabase", "planetscale", "neon", "turso",
    "brex", "ramp", "gusto", "rippling", "deel", "remote", "lattice",
    "carta", "plaid", "marqeta", "affirm", "chime", "sofi", "robinhood",
    "coinbase", "kraken", "gemini", "consensys",
    "scale", "scaleai", "scale-ai", "huggingface", "cohere", "anthropic",
    "mistral", "perplexity", "cursor", "replit", "sourcegraph", "codeium",
    "anduril", "palantir", "samsara", "verkada", "axon",
    "stripe", "square", "adyen", "checkout", "wise",
    "shopify", "klaviyo", "attentive", "yotpo",
    "databricks", "snowflake", "dbt-labs", "fivetran", "airbyte",
    "elastic", "mongodb", "redis", "cockroachdb", "yugabyte", "clickhouse",
    "cloudflare", "fastly", "akamai", "netlify",
    "hashicorp", "pulumi", "spacelift", "env0",
    "datadog", "newrelic", "honeycomb", "grafana", "chronosphere",
    "crowdstrike", "sentinelone", "lacework", "wiz", "snyk", "orca",
    "github", "gitlab", "jetbrains", "postman", "insomnia",
    "asana", "notion", "coda", "airtable", "monday",
    "zendesk", "intercom", "freshworks", "hubspot", "salesloft", "outreach",
    "gong", "chorus", "clari", "groove",
    "duolingo", "coursera", "udemy", "masterclass",
    "roblox", "epicgames", "riotgames", "unity",
    "navan", "tripactions", "expensify", "brex",
    "benchling", "veeva", "medidata", "flatiron",
    "faire", "attentive", "klaviyo",
    "squarespace", "wix", "webflow",
    "twilio", "sendgrid", "mailchimp", "klaviyo",
    "okta", "auth0", "ping",
    "pagerduty", "victorops", "opsgenie",
    "amplitude", "mixpanel", "segment", "heap",
]


def _slug_variations(name: str) -> list[str]:
    """Generate common slug variations for a company name."""
    base = name.lower().strip()
    return list(dict.fromkeys([
        base,
        base.replace(" ", ""),
        base.replace(" ", "-"),
        base.replace(".", ""),
        base.replace(".", "-"),
        base + "inc",
        base + "-inc",
        base.replace(" ", "") + "inc",
    ]))


def probe(slug: str, client: httpx.Client) -> tuple[bool, int]:
    """Returns (is_valid, job_count). is_valid=False means 404."""
    try:
        resp = client.get(_API.format(slug=slug), timeout=10)
        if resp.status_code == 404:
            return False, 0
        data = resp.json()
        if isinstance(data, list):
            return True, len(data)
        return False, 0
    except Exception:
        return False, 0


def run(min_jobs: int = 0):
    found = []
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as client:
        seen = set()
        for name in _COMPANY_NAMES:
            for slug in _slug_variations(name):
                if slug in seen:
                    continue
                seen.add(slug)
                valid, count = probe(slug, client)
                if valid:
                    logger.info(f"✅ {slug} → {count} jobs")
                    if count >= min_jobs:
                        found.append({"name": slug.replace("-", " ").title(), "slug": slug, "jobs": count})
                time.sleep(0.15)

    found.sort(key=lambda x: x["jobs"], reverse=True)

    out = Path(__file__).parent / "companies_discovered.json"
    out.write_text(json.dumps(found, indent=2))
    logger.info(f"Found {len(found)} valid slugs → saved to {out}")
    logger.info("Companies with jobs:")
    for c in found:
        if c["jobs"] > 0:
            logger.info(f"  {c['slug']}: {c['jobs']} jobs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-jobs", type=int, default=0)
    args = parser.parse_args()
    run(min_jobs=args.min_jobs)
