"""
Shared filter helpers used by every scraper.
"""
import re

_CAMEL_SPLIT_RE = re.compile(r'[A-Z][a-z]+|[A-Z]+(?=[A-Z][a-z])|[A-Z]+$|[a-z]+')

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

# Suffixes stripped before checking if company name appears in description.
# Removes legal/generic words so "AgileGrid Solutions" → "AgileGrid",
# "Google LLC" → "Google", "Quik Hire Staffing" → "Quik Hire".
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(LLC|Inc\.?|Corp\.?|Ltd\.?|LLP|PLC|GmbH|Co\.?|Holdings?|"
    r"Technologies?|Technology|Services?|Solutions?|Consulting|Consultants?|"
    r"Partners?|Group|Resources?|Staffing|Recruiting|Recruitment|Talent|"
    r"Staffing Solutions|Hiring)\b\.?,?",
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
    # State code wins over ambiguous city names — "Dublin, CA" has CA so it's US,
    # even though "dublin" also matches the Ireland entry in NON_US_KEYWORDS.
    if _US_STATE_CODE_RE.search(location):
        return True
    if any(kw in loc for kw in US_KEYWORDS):
        return True
    if any(kw in loc for kw in NON_US_KEYWORDS):
        return False
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


def company_mentioned_in_description(company_name: str | None, description: str | None) -> tuple[bool, str]:
    """
    Direct employers always reference themselves somewhere in the job description
    ("Join us at Stripe...", "At Google we..."). Staffing agencies post on behalf
    of unnamed clients — their own name never appears.

    Strips generic/legal suffixes to extract the distinctive core, then checks
    if that core appears in the description text.

    Returns (True, "") to keep the job, or (False, reason) to discard.
    """
    if not company_name or not description or len(description.strip()) < 150:
        return True, ""

    core = _COMPANY_SUFFIX_RE.sub("", company_name).strip(" ,&").strip()

    if len(core) < 4:
        return True, ""

    desc_lower = description.lower()

    # Check full distinctive name first (most precise).
    if core.lower() in desc_lower:
        return True, ""

    # Fallback: first space-separated word long enough to be distinctive (≥ 5 chars).
    words = [w for w in core.split() if len(w) >= 5]
    if words and words[0].lower() in desc_lower:
        return True, ""

    # Fallback: CamelCase split — "MetroPlusHealth" → ["Metro","Plus","Health"]
    # Check consecutive pairs (e.g. "MetroPlus") and individual parts ≥ 6 chars.
    camel = _CAMEL_SPLIT_RE.findall(core)
    for i in range(len(camel)):
        # Pair: "MetroPlus", "PlusHealth"
        if i + 1 < len(camel):
            pair = (camel[i] + camel[i + 1]).lower()
            if len(pair) >= 7 and pair in desc_lower:
                return True, ""
        # Single part: only if long enough to be distinctive
        if len(camel[i]) >= 7 and camel[i].lower() in desc_lower:
            return True, ""

    return False, f"'{core}' not found in description"


def company_is_established(
    follower_count: int | None,
    employee_count: int | None,
    follower_threshold: int = 20_000,
    employee_threshold: int = 1_000,
) -> bool:
    """
    Returns True if the company appears to be an established organisation —
    not a fly-by-night staffing agency — based on LinkedIn signals.

    Either condition is sufficient:
      - followers >= 1,000  (1,952 followers → True)
      - employees >= 1,000  (10,001+ employees → True)
    """
    if follower_count is not None and follower_count >= follower_threshold:
        return True
    if employee_count is not None and employee_count >= employee_threshold:
        return True
    return False


# Backward-compat alias used by repository.py
def company_passes_follower_threshold(
    follower_count: int | None,
    threshold: int = 20_000,
    employee_count: int | None = None,
) -> bool:
    return company_is_established(follower_count, employee_count, threshold)
