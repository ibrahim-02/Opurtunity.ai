"""
Auto-discover all Ashby customers from their marketing site and update companies.json.

Source: Ashby blog page embeds a full customerProfiles list in __NEXT_DATA__ JSON.
This covers all sectors: tech, fintech, healthcare, legal, media, hardware, energy, etc.

Usage:
    python -m scrapers.ashby.discover               # fetch + write companies.json
    python -m scrapers.ashby.discover --dry-run     # print counts only, no write
"""
import argparse
import json
import re
import sys
from pathlib import Path

import requests
from loguru import logger

ASHBY_BLOG = "https://www.ashbyhq.com/blog"
COMPANIES_FILE = Path(__file__).parent / "companies.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-scraper/1.0)"}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def _get_next_data(url: str) -> dict:
    try:
        r = requests.get(url, timeout=20, headers=HEADERS)
        r.raise_for_status()
    except Exception as exc:
        logger.warning("Could not fetch {}: {}", url, exc)
        return {}
    m = NEXT_DATA_RE.search(r.text)
    if not m:
        logger.warning("No __NEXT_DATA__ found on {}", url)
        return {}
    return json.loads(m.group(1))


def discover_customers() -> dict[str, str]:
    """
    Return {slug: name} for all Ashby customers found in the blog __NEXT_DATA__.
    The blog page ships a full customerProfiles list used by its sidebar.
    """
    logger.info("Fetching Ashby customer list from {}", ASHBY_BLOG)
    data = _get_next_data(ASHBY_BLOG)

    profiles: list[dict] = (
        data.get("props", {}).get("pageProps", {}).get("customerProfiles", [])
    )
    if not profiles:
        logger.warning("customerProfiles not found — falling back to deep JSON scan")
        profiles = _deep_find_profiles(data)

    result: dict[str, str] = {}
    for p in profiles:
        slug = (p.get("slug") or "").strip()
        name = (p.get("name") or "").strip()
        if slug and name and slug not in result:
            result[slug] = name

    logger.info("Found {} customer profiles", len(result))
    return result


def _deep_find_profiles(obj, found=None) -> list[dict]:
    """Fallback: walk arbitrary JSON tree looking for company-shaped dicts."""
    if found is None:
        found = []
    if isinstance(obj, dict):
        if "slug" in obj and "name" in obj and ("logo" in obj or "website" in obj):
            found.append(obj)
        for v in obj.values():
            _deep_find_profiles(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _deep_find_profiles(item, found)
    return found


def load_existing() -> dict[str, str]:
    """Return {slug: name} from the current companies.json."""
    if not COMPANIES_FILE.exists():
        return {}
    return {e["slug"]: e["name"] for e in json.loads(COMPANIES_FILE.read_text())}


def merge(existing: dict[str, str], discovered: dict[str, str]) -> list[dict]:
    """
    Merge discovered + existing:
    - For slugs already in existing, keep the existing human-curated name.
    - New slugs from discovered are added with Ashby's display name.
    - Sort alphabetically by slug.
    """
    merged: dict[str, str] = {}

    # Start with discovered (Ashby's own names)
    for slug, name in discovered.items():
        merged[slug] = name

    # Existing entries override (they have verified slugs + curated names)
    for slug, name in existing.items():
        merged[slug] = name

    return [
        {"name": name, "slug": slug}
        for slug, name in sorted(merged.items(), key=lambda x: x[0].lower())
    ]


def main():
    parser = argparse.ArgumentParser(description="Discover all Ashby companies")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print counts only — do not write companies.json")
    args = parser.parse_args()

    discovered = discover_customers()
    if not discovered:
        logger.error("No companies discovered — check network or Ashby site structure")
        sys.exit(1)

    existing = load_existing()
    new_slugs = [s for s in discovered if s not in existing]

    logger.info(
        "Discovered {} companies | existing={} new={}",
        len(discovered), len(existing), len(new_slugs),
    )
    if new_slugs:
        logger.info("New companies:\n  {}", "\n  ".join(
            f"{s} ({discovered[s]})" for s in sorted(new_slugs)
        ))

    if args.dry_run:
        logger.info("Dry-run — companies.json not modified")
        return

    companies = merge(existing, discovered)
    COMPANIES_FILE.write_text(json.dumps(companies, indent=2, ensure_ascii=False))
    logger.info("Written {} companies to {}", len(companies), COMPANIES_FILE)


if __name__ == "__main__":
    main()
