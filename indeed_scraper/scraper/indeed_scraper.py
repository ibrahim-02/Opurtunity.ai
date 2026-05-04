import random
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from loguru import logger
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class IndeedScraper:
    BASE_URL = "https://www.indeed.com"
    # Indeed paginates in steps of 10
    JOBS_PER_PAGE = 10

    def __init__(self, headless: bool = False):
        self._headless = headless
        self.driver: uc.Chrome | None = None

    # ── Driver lifecycle ──────────────────────────────────────────────────────

    def _init_driver(self) -> None:
        opts = uc.ChromeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        if self._headless:
            opts.add_argument("--headless=new")
        self.driver = uc.Chrome(options=opts)
        self.driver.implicitly_wait(5)
        logger.info("Chrome driver initialised (headless={}).", self._headless)

    def _quit(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def __enter__(self):
        self._init_driver()
        return self

    def __exit__(self, *_):
        self._quit()

    # ── URL helpers ───────────────────────────────────────────────────────────

    def _search_url(self, query: str, location: str, days: int, start: int) -> str:
        params = {
            "q": query,
            "l": location,
            "fromage": days,   # 1=24h, 3=3days, 7=week, 14=2weeks
            "sort": "date",
            "start": start,
        }
        return f"{self.BASE_URL}/jobs?{urlencode(params)}"

    # ── Bot / challenge detection ─────────────────────────────────────────────

    def _is_challenge(self) -> bool:
        src = self.driver.page_source.lower()
        return any(p in src for p in (
            "checking your browser",
            "are you a robot",
            "unusual traffic",
            "captcha",
            "verify you are human",
            "cf-browser-verification",
        ))

    def _await_challenge(self, timeout: int = 120) -> None:
        logger.warning("Bot challenge detected — waiting up to {}s...", timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._is_challenge():
                logger.info("Challenge cleared.")
                return
            time.sleep(3)
        logger.error("Challenge not resolved — results for this page may be incomplete.")

    # ── Static parsing helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_salary(text: str | None) -> dict | None:
        """
        Converts Indeed salary strings to {"min": float, "max": float, "currency": "USD"}.
        Handles hourly rates by annualising at 2080 hrs/yr.
        Examples: "$80,000 - $120,000 a year", "$25 - $35 an hour"
        """
        if not text:
            return None
        clean = text.replace(",", "")
        nums = re.findall(r"\$?([\d]+(?:\.\d+)?)", clean)
        if not nums:
            return None
        amounts = [float(n) for n in nums[:2]]
        if "hour" in text.lower() or "/hr" in text.lower():
            amounts = [a * 2080 for a in amounts]
        if len(amounts) == 2:
            return {"min": amounts[0], "max": amounts[1], "currency": "USD"}
        return {"min": amounts[0], "max": amounts[0], "currency": "USD"}

    @staticmethod
    def _parse_posted_date(text: str | None) -> datetime:
        """
        Converts Indeed relative date strings to UTC datetime.
        Examples: "2 days ago", "Just posted", "30+ days ago"
        """
        now = datetime.now(timezone.utc)
        if not text:
            return now
        t = text.lower().strip()
        if any(w in t for w in ("just", "today", "hour", "moment", "active")):
            return now
        m = re.search(r"(\d+)\s+day", t)
        if m:
            return now - timedelta(days=int(m.group(1)))
        if "30+" in t or "month" in t:
            return now - timedelta(days=30)
        return now

    # ── Card parsing (BeautifulSoup) ──────────────────────────────────────────

    def _parse_card(self, card: BeautifulSoup) -> dict | None:
        # Title + job key — try multiple selectors for resilience
        title_a = (
            card.select_one("h2.jobTitle a[data-jk]")
            or card.select_one("a[data-jk]")
            or card.select_one("h2 a")
            or card.select_one(".jobTitle a")
        )
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        job_key = title_a.get("data-jk", "")
        href = title_a.get("href", "")
        if job_key:
            link = f"{self.BASE_URL}/viewjob?jk={job_key}"
        elif href.startswith("http"):
            link = href
        elif href:
            link = self.BASE_URL + href
        else:
            return None  # no usable link

        if not title:
            return None

        # Company
        company_el = (
            card.select_one("[data-testid='company-name']")
            or card.select_one(".companyName")
        )
        company = company_el.get_text(strip=True) if company_el else None

        # Location
        loc_el = (
            card.select_one("[data-testid='text-location']")
            or card.select_one(".companyLocation")
        )
        location = loc_el.get_text(strip=True) if loc_el else None

        # Salary (not always present)
        sal_el = (
            card.select_one("[data-testid='attribute_snippet_testid']")
            or card.select_one(".salary-snippet-container")
            or card.select_one(".estimated-salary")
            or card.select_one("[data-testid='jobsearch-SerpJobCard-salaryEst']")
        )
        salary_text = sal_el.get_text(strip=True) if sal_el else None

        # Posted date
        date_el = (
            card.select_one("span.date")
            or card.select_one("[data-testid='myJobsStateDate']")
            or card.select_one(".result-footer span")
        )
        posted_text = date_el.get_text(strip=True) if date_el else None

        return {
            "title": title,
            "company": company,
            "location": location,
            "salary_text": salary_text,
            "posted_text": posted_text,
            "link": link,
            "job_key": job_key,
        }

    # ── Page-level scraping ───────────────────────────────────────────────────

    def _load_page(self, url: str) -> bool:
        """Navigate to URL and wait for job cards to appear. Returns False if none found."""
        self.driver.get(url)
        time.sleep(random.uniform(2, 4))
        if self._is_challenge():
            self._await_challenge()
        try:
            WebDriverWait(self.driver, 12).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "div.job_seen_beacon, [data-testid='slider_item'], .resultContent",
                ))
            )
            return True
        except TimeoutException:
            return False

    def _has_next_page(self) -> bool:
        try:
            self.driver.find_element(
                By.CSS_SELECTOR,
                "[data-testid='pagination-page-next'], a[aria-label='Next Page'], a[aria-label='Next']",
            )
            return True
        except Exception:
            return False

    def _scrape_results_page(self, url: str) -> list[dict]:
        if not self._load_page(url):
            logger.warning("No job cards detected at: {}", url)
            return []

        soup = BeautifulSoup(self.driver.page_source, "lxml")

        # Try both card selector patterns
        cards = soup.select("div.job_seen_beacon")
        if not cards:
            cards = soup.select("[data-testid='slider_item']")
        if not cards:
            # Broader fallback
            cards = soup.select("li.css-5lfssm, li[class*='ResultsList']")

        jobs = []
        for card in cards:
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.debug("Card parse error: {}", e)

        return jobs

    # ── Job description fetching ──────────────────────────────────────────────

    def _fetch_description(self, job_key: str) -> str | None:
        """Open the individual job page and extract the description text."""
        if not job_key:
            return None
        url = f"{self.BASE_URL}/viewjob?jk={job_key}"
        try:
            self.driver.get(url)
            time.sleep(random.uniform(2, 3))
            if self._is_challenge():
                self._await_challenge()
            soup = BeautifulSoup(self.driver.page_source, "lxml")
            desc = (
                soup.select_one("div#jobDescriptionText")
                or soup.select_one(".jobsearch-jobDescriptionText")
                or soup.select_one("[data-testid='jobsearch-JobComponent-description']")
            )
            return desc.get_text(separator="\n", strip=True) if desc else None
        except Exception as e:
            logger.debug("Description fetch failed for jk={}: {}", job_key, e)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def scrape_query(
        self,
        query: str,
        location: str = "United States",
        days: int = 1,
        max_pages: int = 5,
        fetch_descriptions: bool = True,
    ) -> list[dict]:
        """
        Scrape Indeed for `query`, returning a list of enriched job dicts.
        Each dict has keys: title, company, location, salary_text, posted_text,
        link, job_key, description.
        """
        if self.driver is None:
            self._init_driver()

        all_jobs: list[dict] = []

        for page in range(max_pages):
            start = page * self.JOBS_PER_PAGE
            url = self._search_url(query, location, days, start)
            logger.info("  Page {}/{} | start={} | {}", page + 1, max_pages, start, url)

            cards = self._scrape_results_page(url)
            if not cards:
                logger.info("  Empty page — stopping pagination for '{}'.", query)
                break

            logger.info("  {} cards found on page {}.", len(cards), page + 1)

            if fetch_descriptions:
                for card in cards:
                    if card.get("job_key"):
                        card["description"] = self._fetch_description(card["job_key"])
                        time.sleep(random.uniform(2, 4))
                    else:
                        card["description"] = None
            else:
                for card in cards:
                    card["description"] = None

            all_jobs.extend(cards)

            if not self._has_next_page():
                logger.info("  No next-page button — done with '{}'.", query)
                break

            time.sleep(random.uniform(3, 6))

        return all_jobs
