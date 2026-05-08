"""
Workday CXS API client.

POST /wday/cxs/{tenant}/{career_site}/jobs    → paginated job listings
GET  /wday/cxs/{tenant}/{career_site}/job/... → per-job description HTML
"""
import re

import httpx
from bs4 import BeautifulSoup
from loguru import logger

import scrapers.workday.settings as _cfg


def _base(tenant: str, wd_num: int) -> str:
    return f"https://{tenant}.wd{wd_num}.myworkdayjobs.com"


def _job_url(tenant: str, wd_num: int, external_path: str) -> str:
    """Canonical web URL for a job — stored as the unique link in the DB."""
    return f"{_base(tenant, wd_num)}{external_path}"


def _api_job_path(external_path: str, career_site: str) -> str:
    """
    Strip locale + career_site prefix from externalPath to get the CXS detail path.
    '/en-US/External_Careers/job/NYC/Engineer_JR-123' → '/job/NYC/Engineer_JR-123'
    """
    # Remove locale segment
    path = re.sub(r"^/[a-z]{2}[-_][A-Za-z]{2}/", "/", external_path, flags=re.I)
    # Remove career_site segment
    path = re.sub(rf"^/{re.escape(career_site)}", "", path, flags=re.I)
    return path


def fetch_jobs(
    tenant: str,
    wd_num: int,
    career_site: str,
    client: httpx.Client,
    offset: int = 0,
    limit: int = _cfg.JOBS_PER_PAGE,
) -> dict:
    """
    Returns raw API response dict with keys:
      total, jobPostings (list of posting dicts)
    Raises httpx.HTTPStatusError on non-2xx.
    """
    url = f"{_base(tenant, wd_num)}/wday/cxs/{tenant}/{career_site}/jobs"
    body = {
        "appliedFacets": {},
        "limit": limit,
        "offset": offset,
        "searchText": "",
    }
    r = client.post(url, json=body, timeout=_cfg.REQUEST_TIMEOUT,
                    headers={**_cfg._HEADERS, "Content-Type": "application/json"})
    r.raise_for_status()
    return r.json()


def fetch_job_description(
    tenant: str,
    wd_num: int,
    career_site: str,
    external_path: str,
    client: httpx.Client,
) -> str | None:
    """
    Fetch the job detail from the CXS API.
    Returns plain-text description or None on failure.
    """
    api_path = _api_job_path(external_path, career_site)
    url = f"{_base(tenant, wd_num)}/wday/cxs/{tenant}/{career_site}{api_path}"
    try:
        r = client.get(url, timeout=_cfg.REQUEST_TIMEOUT, headers=_cfg._HEADERS)
        if r.status_code != 200:
            return None
        data = r.json()
        raw_html = (
            data.get("jobPostingInfo", {}).get("jobDescription")
            or data.get("jobDescription")
            or ""
        )
        if not raw_html:
            return None
        return BeautifulSoup(raw_html, "lxml").get_text(separator="\n", strip=True)
    except Exception as e:
        logger.debug("Description fetch failed for {}: {}", external_path, e)
        return None


def extract_location(posting: dict) -> str | None:
    return posting.get("locationsText") or None


def extract_posted_date(posting: dict) -> str | None:
    return posting.get("postedOn") or None
