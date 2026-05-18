"""
Discover Workday companies from Workday's own public customers page.

Workday lists their customers at workday.com/en-us/customers.html.
We extract company names and feed them through the existing slug-based
brute-force discovery to find their Workday job board URLs.
"""
import re

import httpx
from bs4 import BeautifulSoup
from loguru import logger

CUSTOMERS_URL = "https://www.workday.com/en-us/customers.html"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Workday also publishes per-industry and per-product customer lists
ADDITIONAL_PAGES = [
    "https://www.workday.com/en-us/customers/by-industry/financial-services.html",
    "https://www.workday.com/en-us/customers/by-industry/healthcare.html",
    "https://www.workday.com/en-us/customers/by-industry/higher-education.html",
    "https://www.workday.com/en-us/customers/by-industry/professional-services.html",
    "https://www.workday.com/en-us/customers/by-industry/retail.html",
    "https://www.workday.com/en-us/customers/by-industry/technology.html",
    "https://www.workday.com/en-us/customers/by-industry/manufacturing.html",
    "https://www.workday.com/en-us/customers/by-industry/government.html",
]

# Selectors for customer names on Workday's site (update if their HTML changes)
_NAME_SELECTORS = [
    "[data-automation-id='customerName']",
    ".customer-name",
    ".customer-card__name",
    ".customer__name",
    "h3.heading",
    ".card__title",
    "figure figcaption",
    "img[alt]",   # customer logos often have alt text = company name
]

# Patterns that indicate a string is NOT a company name
_NOISE_RE = re.compile(
    r"^(read|watch|learn|view|case study|story|video|customer|see how|"
    r"explore|download|get started|more|next|previous|\d+)$",
    re.IGNORECASE,
)


def _scrape_names_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    names: set[str] = set()

    for sel in _NAME_SELECTORS:
        for el in soup.select(sel):
            # For img tags, use alt attribute
            text = el.get("alt", "") if el.name == "img" else el.get_text(" ", strip=True)
            text = text.strip()
            if (
                text
                and 2 < len(text) < 80
                and not _NOISE_RE.match(text)
            ):
                names.add(text)

    return list(names)


def fetch_customer_names() -> list[str]:
    """
    Fetch Workday customer pages and return all company names found.
    Deduplicates across pages.
    """
    all_names: set[str] = set()
    pages = [CUSTOMERS_URL] + ADDITIONAL_PAGES

    with httpx.Client(follow_redirects=True, headers=HEADERS, timeout=20.0) as client:
        for url in pages:
            try:
                r = client.get(url)
                if r.status_code != 200:
                    logger.debug("  {} → HTTP {}", url, r.status_code)
                    continue
                names = _scrape_names_from_html(r.text)
                logger.info("  {} → {} names", url, len(names))
                all_names.update(names)
            except Exception as exc:
                logger.warning("  Failed to fetch {}: {}", url, exc)

    result = sorted(all_names)
    logger.info("Total unique customer names from Workday site: {}", len(result))
    return result
