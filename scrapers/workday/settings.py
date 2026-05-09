"""Workday-scraper-specific configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

SEC_COMPANIES_TABLE = "public.sec_companies"

# All 5 wd server variants tried concurrently per slug
WD_NUMS = [1, 2, 3, 4, 5]

CONCURRENCY = int(os.getenv("WD_CONCURRENCY", "25"))
REQUEST_DELAY = float(os.getenv("WD_REQUEST_DELAY", "0.5"))
REQUEST_TIMEOUT = float(os.getenv("WD_REQUEST_TIMEOUT", "8.0"))
CONNECT_TIMEOUT = float(os.getenv("WD_CONNECT_TIMEOUT", "3.0"))

JOBS_PER_PAGE = 20
MAX_PAGES = 50           # hard cap: 1000 jobs per company

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
