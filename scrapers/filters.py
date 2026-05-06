"""
Shared filter helpers used by every scraper.
"""
import re

from scrapers.settings import (
    EXCLUDED_COMPANIES,
    NON_US_KEYWORDS,
    TITLE_EXCLUDE_KEYWORDS,
    TITLE_KEYWORDS,
    US_KEYWORDS,
    US_STATE_CODES,
)

# Pre-compile patterns so each scrape doesn't rebuild them.
_TITLE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(kw.strip()) for kw in TITLE_KEYWORDS if kw.strip()) + r")\b",
    re.IGNORECASE,
)

_US_STATE_CODE_RE = re.compile(r"\b(?:" + "|".join(US_STATE_CODES) + r")\b")

# Word-boundary regex so 'lever' doesn't match 'Unilever', 'tti' doesn't match 'Lattice'.
_EXCLUDED_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(b.strip()) for b in EXCLUDED_COMPANIES if b.strip()) + r")\b",
    re.IGNORECASE,
)


def passes_title(title: str | None) -> bool:
    """
    Word-boundary match — 'bi' hits 'BI Developer' but not 'habit'.
    Also rejects titles containing any TITLE_EXCLUDE_KEYWORDS phrase.
    """
    if not title:
        return False
    t_low = title.lower()
    if any(ex in t_low for ex in TITLE_EXCLUDE_KEYWORDS):
        return False
    return bool(_TITLE_RE.search(title))


def is_us_location(location: str | None) -> bool:
    """
    Strict US-only check.
    Rejects: explicit non-US cities/countries, regional tags (EMEA/APAC),
             bare 'Remote' (could be anywhere).
    Accepts: US states (code or full name), 'United States', 'USA',
             'Remote - US' / 'US Remote' patterns.
    """
    if not location:
        return False
    loc = location.lower().strip()
    if any(kw in loc for kw in NON_US_KEYWORDS):
        return False
    if any(kw in loc for kw in US_KEYWORDS):
        return True
    if _US_STATE_CODE_RE.search(location):
        return True
    return False


def is_us_location_multi(locations: list[str]) -> bool:
    """For Greenhouse — a job exposes multiple location strings (offices, allLocations)."""
    if not locations:
        return False
    combined = " | ".join(locations)
    return is_us_location(combined)


def is_excluded_company(name: str | None) -> bool:
    """
    Word-boundary match so single-word entries don't false-positive:
      - 'lever'        does NOT match 'Unilever'
      - 'tti'          does NOT match 'Lattice'
      - 'robert half'  DOES match 'Robert Half Technology'
    """
    if not name:
        return False
    return bool(_EXCLUDED_RE.search(name))
