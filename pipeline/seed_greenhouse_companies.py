"""
Seed the greenhouse_companies table with known Greenhouse ATS companies.
All slugs verified against boards-api.greenhouse.io.

Usage:
    python -m pipeline.seed_greenhouse_companies
"""
import sys
from loguru import logger
from sqlalchemy import text
from database.connection import SessionLocal

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

COMPANIES = [
    # Big Tech & Cloud
    ("Stripe",              "stripe"),
    ("Airbnb",              "airbnb"),
    ("Lyft",                "lyft"),
    ("Discord",             "discord"),
    ("Figma",               "figma"),
    ("Dropbox",             "dropbox"),
    ("Block",               "block"),
    ("Vercel",              "vercel"),
    ("Cloudflare",          "cloudflare"),
    ("MongoDB",             "mongodb"),
    ("Databricks",          "databricks"),
    ("Twilio",              "twilio"),
    ("Okta",                "okta"),
    ("Affirm",              "affirm"),
    ("HubSpot",             "hubspot"),
    ("Duolingo",            "duolingo"),
    ("Robinhood",           "robinhood"),
    ("Brex",                "brex"),
    ("Gusto",               "gusto"),
    ("Airtable",            "airtable"),
    # Already in DB but keep for idempotency
    ("Coinbase",            "coinbase"),
    ("Datadog",             "datadog"),
    ("Life360",             "life360"),
    ("Chime",               "chime"),
    ("Toast",               "toast"),
    ("NICE Ltd.",           "nice"),
    ("Omada Health",        "omadahealth"),
    ("Array",               "array"),
    # Security & Infra
    ("CrowdStrike",         "crowdstrike"),
    ("SentinelOne",         "sentinelone"),
    ("Palo Alto Networks",  "paloaltonetworks"),
    ("Wiz",                 "wiz-inc"),
    ("Lacework",            "lacework"),
    ("Snyk",                "snyk"),
    ("Cybereason",          "cybereason"),
    ("Orca Security",       "orca-security"),
    # Data & Analytics
    ("dbt Labs",            "dbt-labs"),
    ("Fivetran",            "fivetran"),
    ("Segment",             "segment"),
    ("Amplitude",           "amplitude"),
    ("Mixpanel",            "mixpanel"),
    ("Looker",              "looker"),
    ("Starburst",           "starburst-data"),
    ("Monte Carlo",         "montecarlodata"),
    # AI & ML
    ("Scale AI",            "scaleai"),
    ("Hugging Face",        "huggingface"),
    ("Cohere",              "cohere"),
    ("Weights & Biases",    "wandb"),
    ("LlamaIndex",          "llamaindex"),
    ("Anthropic",           "anthropic"),
    ("Mistral AI",          "mistral"),
    ("Perplexity AI",       "perplexity"),
    # Fintech
    ("Plaid",               "plaid"),
    ("Marqeta",             "marqeta"),
    ("Checkout.com",        "checkout"),
    ("Carta",               "carta"),
    ("Rippling",            "rippling"),
    ("Ramp",                "ramp"),
    # Healthcare & Biotech
    ("Oscar Health",        "oscar"),
    ("Hims & Hers",         "forhims"),
    ("Noom",                "noom"),
    ("Ro",                  "ro"),
    ("Benchling",           "benchling"),
    # E-commerce & Marketplace
    ("Faire",               "faire"),
    ("Instacart",           "maplebear"),
    ("Poshmark",            "poshmark"),
    ("Vroom",               "vroom"),
    ("Carvana",             "carvana"),
    # Enterprise SaaS
    ("Asana",               "asana"),
    ("Monday.com",          "mondaydotcom"),
    ("Zendesk",             "zendesk"),
    ("Intercom",            "intercom"),
    ("Freshworks",          "freshworks"),
    ("Salesloft",           "salesloft"),
    ("Gong",                "gong-io"),
    ("Outreach",            "outreach"),
    ("Lattice",             "lattice"),
    ("Leapsome",            "leapsome"),
    # Dev Tools
    ("HashiCorp",           "hashicorp"),
    ("Sourcegraph",         "sourcegraph"),
    ("Grafana Labs",        "grafana-labs"),
    ("PagerDuty",           "pagerduty"),
    ("LaunchDarkly",        "launchdarkly"),
    ("Retool",              "retool"),
    ("Temporal",            "temporal-technologies"),
    # Gaming
    ("Roblox",              "roblox"),
    ("Epic Games",          "epicgames"),
    ("Riot Games",          "riotgames"),
    ("Unity",               "unity-technologies"),
    ("Niantic",             "niantic-inc"),
    # Media & Consumer
    ("Reddit",              "reddit"),
    ("Pinterest",           "pinterest"),
    ("Snap",                "snap"),
    ("Bumble",              "bumble"),
    ("Duolingo",            "duolingo"),
    # Misc High-Growth
    ("Anduril",             "anduril"),
    ("Palantir",            "palantir"),
    ("SpaceX",              "spacex"),
    ("Samsara",             "samsara"),
    ("Verkada",             "verkada"),
    ("Navan",               "navan"),
    ("Loom",                "loom"),
    ("Notion",              "notion"),
]


def run():
    session = SessionLocal()
    added = skipped = 0

    for name, slug in COMPANIES:
        exists = session.execute(
            text("SELECT id FROM greenhouse_companies WHERE slug = :slug"),
            {"slug": slug}
        ).fetchone()
        if exists:
            skipped += 1
            continue
        session.execute(text("""
            INSERT INTO greenhouse_companies (company_name, slug, active)
            VALUES (:name, :slug, true)
            ON CONFLICT (slug) DO NOTHING
        """), {"name": name, "slug": slug})
        added += 1

    session.commit()
    session.close()
    logger.info(f"Seeded {added} new companies, {skipped} already existed")
    logger.info("Run: python -m scrapers.greenhouse.main --scrape")


if __name__ == "__main__":
    run()
