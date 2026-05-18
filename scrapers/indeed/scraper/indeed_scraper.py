import os
import random
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from loguru import logger
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

# Persistent Chrome profile — cookies survive between runs so Cloudflare
# doesn't treat every session as a fresh bot.
_PROFILE_DIR = str(Path(__file__).resolve().parent.parent / "chrome_profile")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)


def _installed_chrome_major() -> int | None:
    """Read installed Chrome major version from the Windows registry."""
    try:
        result = subprocess.run(
            ["reg", "query", r"HKLM\SOFTWARE\Google\Chrome\BLBeacon", "/v", "version"],
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(r"(\d+)\.\d+\.\d+\.\d+", result.stdout)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


class IndeedScraper:
    BASE_URL = "https://www.indeed.com"
    JOBS_PER_PAGE = 10

    def __init__(self, headless: bool = False):
        self._headless = headless
        self.driver: uc.Chrome | None = None

    # ── Driver lifecycle ──────────────────────────────────────────────────────

    def _init_driver(self) -> None:
        os.makedirs(_PROFILE_DIR, exist_ok=True)

        opts = uc.ChromeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(f"--user-agent={_USER_AGENT}")
        opts.add_argument(f"--user-data-dir={_PROFILE_DIR}")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--lang=en-US")
        if self._headless:
            opts.add_argument("--headless=new")

        chrome_major = _installed_chrome_major()
        if chrome_major:
            logger.info("Detected Chrome {} — pinning ChromeDriver.", chrome_major)
            self.driver = uc.Chrome(options=opts, version_main=chrome_major)
        else:
            self.driver = uc.Chrome(options=opts)

        # Hide all automation signals Cloudflare checks
        stealth(
            self.driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

        # CDP-level overrides that survive page navigation
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                });
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8,
                });
                window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
                const orig = window.HTMLIFrameElement.prototype.contentWindow;
                Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                    get: function() {
                        const w = orig.call(this);
                        if (!w) return w;
                        try {
                            Object.defineProperty(w, 'webdriver', {get: () => undefined});
                        } catch(e) {}
                        return w;
                    }
                });
            """
        })

        self.driver.implicitly_wait(5)
        logger.info("Chrome driver initialised (headless={}).", self._headless)

    def _has_signin_button(self) -> bool:
        """True when the Sign In link is visible in the header = not logged in."""
        try:
            self.driver.find_element(
                By.CSS_SELECTOR,
                "header a[href*='/account/login'], "
                "nav a[href*='/account/login'], "
                "[data-gnav-element-name='SignIn'], "
                "a[data-tn-element='header-signin-link']",
            )
            return True
        except Exception:
            return False

    def _ensure_logged_in(self) -> None:
        """
        Visit the Indeed homepage and check for the Sign In button.
        If present (= not logged in), navigate to the login page and wait
        for manual sign-in (session is saved to chrome_profile/ for all future runs).
        """
        self.driver.get(self.BASE_URL)
        time.sleep(3)
        if self._is_challenge():
            self._await_challenge()

        if not self._has_signin_button():
            logger.info("Already signed in to Indeed (session from profile).")
            return

        logger.warning(
            "Not signed in to Indeed — opening login page. "
            "Please sign in in the browser window (waiting up to 3 min)..."
        )
        self.driver.get(f"{self.BASE_URL}/account/login")
        time.sleep(2)

        deadline = time.time() + 180
        while time.time() < deadline:
            time.sleep(3)
            # After successful sign-in Indeed redirects to homepage —
            # the Sign In button disappears from the nav.
            if not self._has_signin_button():
                logger.info("Sign-in complete — session saved to chrome_profile/.")
                return

        logger.warning("Sign-in not completed within 3 min — proceeding (expect more challenges).")

    def _quit(self) -> None:
        if self.driver:
            d = self.driver
            self.driver = None
            try:
                d.quit()
            except Exception:
                pass
            # Prevent undetected_chromedriver __del__ from raising WinError 6
            try:
                d.service.process = None
            except Exception:
                pass

    def __enter__(self):
        self._init_driver()
        self._ensure_logged_in()
        return self

    def __exit__(self, *_):
        self._quit()

    # ── URL ───────────────────────────────────────────────────────────────────

    def _search_url(self, query: str, location: str, days: int, start: int) -> str:
        params = {"q": query, "l": location, "fromage": days, "sort": "date", "start": start}
        return f"{self.BASE_URL}/jobs?{urlencode(params)}"

    # ── Bot detection ─────────────────────────────────────────────────────────

    def _is_challenge(self) -> bool:
        src = self.driver.page_source.lower()
        return any(p in src for p in (
            "checking your browser", "are you a robot",
            "unusual traffic", "captcha", "verify you are human",
            "additional verification required", "ray id",
        ))

    def _try_click_cloudflare(self) -> bool:
        """
        Click the Cloudflare 'Verify you are human' checkbox. It's hidden in
        an iframe — switch context, click with a slight offset (more human-like),
        switch back. Returns True if a click was performed.
        """
        from selenium.webdriver.common.action_chains import ActionChains

        iframe_selectors = (
            "iframe[src*='challenges.cloudflare']",
            "iframe[src*='turnstile']",
            "iframe[title*='challenge']",
            "iframe[title*='Cloudflare']",
        )

        # Strategy 1: enter the iframe and click the actual checkbox
        for sel in iframe_selectors:
            try:
                iframes = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for iframe in iframes:
                    try:
                        self.driver.switch_to.frame(iframe)
                        checkbox = WebDriverWait(self.driver, 4).until(
                            EC.element_to_be_clickable(
                                (By.CSS_SELECTOR, "input[type='checkbox'], label.cf-label, .cb-c")
                            )
                        )
                        ActionChains(self.driver) \
                            .move_to_element_with_offset(checkbox, 2, 2) \
                            .pause(random.uniform(0.3, 0.8)) \
                            .click() \
                            .perform()
                        self.driver.switch_to.default_content()
                        logger.info("Clicked Cloudflare checkbox (iframe strategy).")
                        return True
                    except Exception:
                        self.driver.switch_to.default_content()
                        continue
            except Exception:
                continue

        # Strategy 2: click the iframe area itself with an offset
        for sel in iframe_selectors:
            try:
                iframe = self.driver.find_element(By.CSS_SELECTOR, sel)
                ActionChains(self.driver) \
                    .move_to_element_with_offset(iframe, 30, 30) \
                    .pause(random.uniform(0.4, 0.9)) \
                    .click() \
                    .perform()
                logger.info("Clicked Cloudflare iframe area (offset strategy).")
                return True
            except Exception:
                continue

        return False

    def _await_challenge(self, timeout: int = 120) -> None:
        logger.warning(
            "Bot challenge detected — auto-click + waiting up to {}s... "
            "(if the browser is visible, click the 'Verify you are human' checkbox manually)",
            timeout,
        )
        time.sleep(3)
        self._try_click_cloudflare()

        deadline = time.time() + timeout
        last_retry = time.time()
        while time.time() < deadline:
            if not self._is_challenge():
                logger.info("Challenge cleared.")
                return
            time.sleep(3)
            if time.time() - last_retry > 12:
                self._try_click_cloudflare()
                last_retry = time.time()
        logger.error("Challenge not resolved after {}s — skipping this page.", timeout)

    # ── Parsing helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_salary(text: str | None) -> dict | None:
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

    # ── Card parsing ──────────────────────────────────────────────────────────

    def _parse_card(self, card_html: str) -> dict | None:
        soup = BeautifulSoup(card_html, "lxml")

        title_a = (
            soup.select_one("h2.jobTitle a[data-jk]")
            or soup.select_one("a[data-jk]")
            or soup.select_one("h2 a")
            or soup.select_one(".jobTitle a")
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
            return None

        if not title:
            return None

        company_el = (
            soup.select_one("[data-testid='company-name']")
            or soup.select_one(".companyName")
        )
        company = company_el.get_text(strip=True) if company_el else None

        loc_el = (
            soup.select_one("[data-testid='text-location']")
            or soup.select_one(".companyLocation")
        )
        location = loc_el.get_text(strip=True) if loc_el else None

        sal_el = (
            soup.select_one("[data-testid='attribute_snippet_testid']")
            or soup.select_one(".salary-snippet-container")
            or soup.select_one(".estimated-salary")
        )
        salary_text = sal_el.get_text(strip=True) if sal_el else None

        date_el = (
            soup.select_one("span.date")
            or soup.select_one("[data-testid='myJobsStateDate']")
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

    # ── Page loading ──────────────────────────────────────────────────────────

    def _load_page(self, url: str) -> bool:
        self.driver.get(url)
        time.sleep(random.uniform(2, 4))
        if self._is_challenge():
            self._await_challenge()
        try:
            WebDriverWait(self.driver, 12).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "a[data-jk], div.job_seen_beacon, [data-testid='slider_item'], .resultContent",
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

    # ── LinkedIn-style scroll + collect ──────────────────────────────────────

    def _scroll_and_collect_cards(self) -> dict[str, str]:
        """
        Mirror LinkedIn's scroll strategy:
        - Find the scrollable job-list panel (or fall back to window scroll).
        - Scroll 600px per step, capture card outerHTML by data-jk at each step.
        - Stop after 5 consecutive steps with no new cards.
        Returns dict of {job_key: card_html}.
        """
        panel = self.driver.execute_script("""
            var sels = [
                'div#mosaic-provider-jobcards',
                'div.jobsearch-ResultsList',
                'ul.jobsearch-ResultsList',
                'div.jobs-container',
                'div[id^="mosaic-provider"]'
            ];
            for (var i = 0; i < sels.length; i++) {
                var el = document.querySelector(sels[i]);
                if (el && el.scrollHeight > el.clientHeight + 50) return el;
            }
            return null;
        """)

        if panel:
            logger.info("  Job list panel found (scrollHeight={}px).",
                        self.driver.execute_script("return arguments[0].scrollHeight", panel))
        else:
            logger.info("  No panel — using window scroll.")

        seen: dict[str, str] = {}
        no_new_streak = 0

        for step in range(60):
            try:
                anchors = self.driver.find_elements(By.CSS_SELECTOR, "a[data-jk]")
            except Exception:
                anchors = []

            new_this_step = 0
            for anchor in anchors:
                jk = anchor.get_attribute("data-jk") or ""
                if not jk or jk in seen:
                    continue
                try:
                    card_html = self.driver.execute_script(
                        """
                        var el = arguments[0];
                        var card = el.closest('div.job_seen_beacon')
                                || el.closest('[data-testid="slider_item"]')
                                || el.closest('li')
                                || el.closest('div.resultContent')
                                || el.parentElement;
                        return card ? card.outerHTML : el.outerHTML;
                        """,
                        anchor,
                    )
                except Exception:
                    card_html = f'<div data-jk="{jk}"></div>'
                seen[jk] = card_html
                new_this_step += 1

            if panel:
                self.driver.execute_script(
                    """
                    arguments[0].scrollTop += 600;
                    arguments[0].dispatchEvent(new Event('scroll', {bubbles: true}));
                    window.dispatchEvent(new Event('scroll'));
                    """,
                    panel,
                )
            elif anchors:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'start'});", anchors[-1]
                    )
                    self.driver.execute_script("window.dispatchEvent(new Event('scroll'));")
                except Exception:
                    self.driver.execute_script(
                        "window.scrollBy(0, 600); window.dispatchEvent(new Event('scroll'));"
                    )
            else:
                self.driver.execute_script(
                    "window.scrollBy(0, 600); window.dispatchEvent(new Event('scroll'));"
                )

            time.sleep(random.uniform(1.0, 2.0))

            if new_this_step == 0:
                no_new_streak += 1
                if no_new_streak >= 5:
                    logger.info("  Scroll done at step {} — {} total cards.", step + 1, len(seen))
                    break
            else:
                no_new_streak = 0

        return seen

    # ── Results page scrape ───────────────────────────────────────────────────

    def _scrape_results_page(self, url: str) -> list[dict]:
        if not self._load_page(url):
            logger.warning("No job cards detected at: {}", url)
            return []

        cards_by_key = self._scroll_and_collect_cards()
        logger.info("  {} unique cards collected after scrolling.", len(cards_by_key))

        jobs = []
        for jk, card_html in cards_by_key.items():
            try:
                job = self._parse_card(card_html)
                if job:
                    if not job.get("job_key"):
                        job["job_key"] = jk
                        job["link"] = f"{self.BASE_URL}/viewjob?jk={jk}"
                    jobs.append(job)
            except Exception as e:
                logger.debug("Card parse error jk={}: {}", jk, e)

        return jobs

    # ── Description fetching ──────────────────────────────────────────────────

    def _extract_panel_description(self) -> str | None:
        """Read the job-description panel that appears on the right after clicking a card."""
        _PANEL_SELECTORS = [
            "div#jobDescriptionText",
            ".jobsearch-jobDescriptionText",
            "[data-testid='jobsearch-JobComponent-description']",
            ".job-description",
            "#job-description",
        ]
        try:
            soup = BeautifulSoup(self.driver.page_source, "lxml")
            for sel in _PANEL_SELECTORS:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) > 50:
                        return text
        except Exception:
            pass
        return None

    def _fetch_description_via_panel(self, anchor_jk: str) -> str | None:
        """
        Click the job card on the search results page so Indeed loads its
        description in the right-side detail panel — no page navigation,
        no new Cloudflare check.
        """
        try:
            anchor = self.driver.find_element(
                By.CSS_SELECTOR, f"a[data-jk='{anchor_jk}']"
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", anchor)
            time.sleep(random.uniform(0.4, 0.8))
            anchor.click()
            # Wait for the description panel to appear
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "div#jobDescriptionText, .jobsearch-jobDescriptionText, "
                        "[data-testid='jobsearch-JobComponent-description']",
                    ))
                )
            except TimeoutException:
                pass
            time.sleep(random.uniform(1.0, 1.8))
            return self._extract_panel_description()
        except Exception as e:
            logger.debug("Panel click failed for jk={}: {}", anchor_jk, e)
            return None

    def _fetch_description(self, job_key: str) -> str | None:
        """
        Try the right-panel approach first (click card on results page).
        Fall back to navigating to /viewjob only if the panel returns nothing.
        """
        if not job_key:
            return None

        text = self._fetch_description_via_panel(job_key)
        if text:
            logger.debug("  Description via panel for jk={} ({} chars).", job_key, len(text))
            return text

        # Fallback: navigate to /viewjob (may hit Cloudflare)
        url = f"{self.BASE_URL}/viewjob?jk={job_key}"
        try:
            self.driver.get(url)
            time.sleep(random.uniform(3, 5))
            if self._is_challenge():
                self._await_challenge()
            text = self._extract_panel_description()
            if text:
                logger.debug("  Description via /viewjob for jk={} ({} chars).", job_key, len(text))
            return text
        except Exception as e:
            logger.debug("Description fetch failed jk={}: {}", job_key, e)
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
        if self.driver is None:
            self._init_driver()

        all_jobs: list[dict] = []

        for page in range(max_pages):
            start = page * self.JOBS_PER_PAGE
            url = self._search_url(query, location, days, start)
            logger.info("  Page {}/{} | start={}", page + 1, max_pages, start)

            cards = self._scrape_results_page(url)
            if not cards:
                logger.info("  Empty page — stopping for '{}'.", query)
                break

            logger.info("  {} cards parsed on page {}.", len(cards), page + 1)

            # Check next page NOW while still on the results page.
            # After fetching descriptions the driver navigates away, so
            # _has_next_page() would always return False if checked later.
            has_more = self._has_next_page()

            if fetch_descriptions:
                logger.info("  Fetching descriptions for {} jobs...", len(cards))
                for i, card in enumerate(cards, 1):
                    if card.get("job_key"):
                        card["description"] = self._fetch_description(card["job_key"])
                        logger.info(
                            "  [{}/{}] description: {} chars | '{}'",
                            i, len(cards),
                            len(card["description"]) if card["description"] else 0,
                            card["title"][:50],
                        )
                        time.sleep(random.uniform(4, 8))
                    else:
                        card["description"] = None
            else:
                for card in cards:
                    card["description"] = None

            all_jobs.extend(cards)

            if not has_more:
                logger.info("  No next-page button — done with '{}'.", query)
                break

            time.sleep(random.uniform(2, 4))

        return all_jobs
