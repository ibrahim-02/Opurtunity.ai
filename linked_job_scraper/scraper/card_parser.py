"""
Parse LinkedIn job card HTML into a JobExtracted model.
Extracts all available fields directly from the card without opening the job page.
"""
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from models.pydantic_models import JobExtracted, SalaryInfo


def parse_card(html: str, link: str) -> JobExtracted:
    soup = BeautifulSoup(html, "html.parser")
    return JobExtracted(
        title=_extract_title(soup) or "Unknown Title",
        company_name=_extract_company(soup),
        link=link,
        location=_extract_location(soup),
        posted_date=_extract_posted_date(soup),
        salary=_extract_salary(soup),
    )


# ── Title ─────────────────────────────────────────────────────────────────────

_TITLE_NOISE = re.compile(
    r'\s*(with verification|verified|sponsored|promoted)\s*$',
    re.IGNORECASE,
)


def _clean_title(text: str) -> str:
    return _TITLE_NOISE.sub("", text).strip()


def _extract_title(soup: BeautifulSoup) -> str | None:
    for sel in [
        "a.job-card-container__link",
        "a.job-card-list__title",
        "a[data-control-name='job_card']",
        "a[href*='/jobs/view/']",
    ]:
        el = soup.select_one(sel)
        if el:
            aria = el.get("aria-label", "").strip()
            if aria:
                return _clean_title(aria)
            text = el.get_text(" ", strip=True)
            if text:
                return _clean_title(text)

    for sel in ["strong", "h3", "h2"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return _clean_title(text)

    return None


# ── Company ───────────────────────────────────────────────────────────────────

def _extract_company(soup: BeautifulSoup) -> str | None:
    for sel in [
        ".job-card-container__primary-description",
        ".artdeco-entity-lockup__subtitle",
        ".job-card-container__company-name",
        ".job-card-list__entity-lockup .artdeco-entity-lockup__subtitle",
        "[data-tracking-control-name='public_jobs_jserp-card_company_name']",
    ]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return text
    return None


# ── Location ──────────────────────────────────────────────────────────────────

def _extract_location(soup: BeautifulSoup) -> str | None:
    # The metadata list contains location (first item) and optionally salary (second).
    # Salary items are flagged with a salary-specific class, so skip those.
    for sel in [
        "li.job-card-container__metadata-item",
        "li[class*='metadata-item']",
    ]:
        items = soup.select(sel)
        for item in items:
            # Skip items that are salary-info containers
            classes = " ".join(item.get("class", []))
            if "salary" in classes or "compensation" in classes:
                continue
            text = item.get_text(" ", strip=True)
            # Salary text slipping through: skip if it starts with "$"
            if text and not text.startswith("$"):
                return text

    # Fallback: artdeco caption often holds location in logged-in view
    el = soup.select_one(".artdeco-entity-lockup__caption")
    if el:
        text = el.get_text(" ", strip=True)
        if text:
            return text

    return None


# ── Posted Date ───────────────────────────────────────────────────────────────

def _extract_posted_date(soup: BeautifulSoup) -> datetime | None:
    # 1. <time datetime="…"> ISO attribute — most reliable
    for time_el in soup.find_all("time"):
        dt_str = time_el.get("datetime", "").strip()
        if dt_str:
            try:
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        # Fall back to relative text inside <time>
        result = _parse_relative_time(time_el.get_text(" ", strip=True))
        if result:
            return result

    # 2. Known CSS selectors for the listed-time element
    for sel in [
        ".job-card-container__listed-time",
        ".job-card-list__time-badge",
        "[class*='listed-time']",
        "[class*='time-badge']",
    ]:
        el = soup.select_one(sel)
        if el:
            result = _parse_relative_time(el.get_text(" ", strip=True))
            if result:
                return result

    # 3. Scan footer items for "X hours/days ago" text
    for sel in [
        "li.job-card-list__footer-wrapper",
        "li[class*='footer']",
    ]:
        for item in soup.select(sel):
            result = _parse_relative_time(item.get_text(" ", strip=True))
            if result:
                return result

    return None


def _parse_relative_time(text: str) -> datetime | None:
    if not text:
        return None
    now = datetime.now(tz=timezone.utc)
    text_lower = text.lower()

    if "just now" in text_lower or "moment ago" in text_lower:
        return now

    m = re.search(r"(\d+)\s*(second|minute|hour|day|week)", text_lower)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        delta_map = {
            "second": timedelta(seconds=amount),
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
        }
        return now - delta_map[unit]

    return None


# ── Salary ────────────────────────────────────────────────────────────────────

def _extract_salary(soup: BeautifulSoup) -> SalaryInfo | None:
    # Dedicated salary element
    for sel in [
        ".job-card-container__salary-info",
        "li[class*='salary']",
        "[class*='compensation']",
        "[class*='salary']",
    ]:
        el = soup.select_one(sel)
        if el:
            result = _parse_salary_text(el.get_text(" ", strip=True))
            if result:
                return result

    # Salary sometimes lives in a metadata-item starting with "$"
    for item in soup.select("li.job-card-container__metadata-item, li[class*='metadata-item']"):
        text = item.get_text(" ", strip=True)
        if text.startswith("$"):
            result = _parse_salary_text(text)
            if result:
                return result

    return None


def _parse_salary_text(text: str) -> SalaryInfo | None:
    """Parse salary strings like '$80K/yr - $120K/yr' or '$40/hr - $60/hr'."""
    if not text:
        return None

    is_hourly = bool(re.search(r'/hr|per hour|hourly', text, re.IGNORECASE))
    clean = text.replace(",", "")

    # Match all dollar amounts with optional K suffix: $80K, $80,000, $80.5K
    numbers = re.findall(r'\$(\d+(?:\.\d+)?)(K?)', clean, re.IGNORECASE)
    if not numbers:
        return None

    vals: list[float] = []
    for num_str, k_suffix in numbers:
        v = float(num_str)
        if k_suffix:
            v *= 1000
        if is_hourly:
            v *= 2080  # annualise: 52 weeks × 40 hrs
        vals.append(v)

    if len(vals) == 1:
        return SalaryInfo(min=vals[0], max=vals[0])
    return SalaryInfo(min=vals[0], max=vals[1])
