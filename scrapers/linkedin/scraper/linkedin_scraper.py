import os
import time
import random
from bs4 import BeautifulSoup
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from loguru import logger

import scrapers.linkedin.settings as _cfg
from scrapers.linkedin.scraper.utils import build_search_url, random_sleep, scroll_page

# Directory to save debug outputs
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs", "debug_screenshots")


def _save_screenshot(driver: WebDriver, name: str):
    """Save a debug screenshot to logs/debug_screenshots/"""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{name}.png")
        driver.save_screenshot(path)
        logger.debug(f"Screenshot saved: {path}")
    except Exception as e:
        logger.warning(f"Could not save screenshot: {e}")


def _save_page_source(driver: WebDriver, name: str):
    """Save full HTML source for debugging CSS selectors."""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{name}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.debug(f"Page source saved: {path}")
    except Exception as e:
        logger.warning(f"Could not save page source: {e}")


def _detect_page_state(driver: WebDriver) -> str:
    current_url = driver.current_url
    title = driver.title
    logger.info(f"Current URL : {current_url}")
    logger.info(f"Page title  : {title}")

    if "checkpoint" in current_url or "captcha" in current_url.lower():
        return "captcha"
    if "login" in current_url or "authwall" in current_url or "uas/login" in current_url:
        return "login_wall"
    if "jobs/search" in current_url or "jobs/results" in current_url:
        return "jobs"
    if "error" in title.lower() or "unavailable" in title.lower():
        return "error"
    return "unknown"


# ── CSS selectors for LOGGED-IN LinkedIn job search page ──
# LinkedIn uses Ember.js rendering when logged in — different from public pages.

WAIT_SELECTORS = ", ".join([
    # Logged-in view
    "div.job-card-container",
    "div.job-card-list",
    "li.jobs-search-results__list-item",
    "div.scaffold-layout__list-container",
    "ul.scaffold-layout__list-container",
    # Also used in logged-in view
    "div[data-job-id]",
    "div.job-card-container--clickable",
    # Public (non-logged-in) view
    "div.base-card",
    "div.job-search-card",
    "ul.jobs-search__results-list",
])

CARD_CSS_SELECTORS = [
    # ── Logged-in selectors (most common first) ──
    "li.scaffold-layout__list-item",
    "li.ember-view.occludable-update",
    "li.jobs-search-results__list-item",
    "div.job-card-container",
    "div.job-card-container--clickable",
    "div[data-job-id]",
    # Container-based: grab <li> inside the results list
    "div.scaffold-layout__list-container > ul > li",
    "ul.scaffold-layout__list-container > li",
    # ── Public (non-logged-in) selectors ──
    "div.base-card",
    "div.base-search-card",
    "div.job-search-card",
    "ul.jobs-search__results-list > li",
]

LINK_SELECTORS = [
    "a.job-card-container__link",
    "a.job-card-list__title",
    "a.disabled.ember-view.job-card-container__link",
    "a[data-control-name='job_card']",
    "a[href*='/jobs/view/']",
    "a.base-card__full-link",
    "a[href*='/jobs/']",
    "a[href]",  # last resort
]


class LinkedInScraper:
    def __init__(self, driver: WebDriver, existing_links: set[str] | None = None):
        self.driver = driver
        # Pre-populate with links already in the DB so duplicates are skipped
        # BEFORE the expensive right-panel description fetch.
        self.seen_links: set[str] = set(existing_links) if existing_links else set()

    def _inject_focus_overrides(self):
        """Patch the page's JavaScript so LinkedIn's lazy loading fires correctly
        even when the Chrome tab is in the background.

        Chrome throttles hidden tabs at three levels:
          1. Page Visibility API  — visibilityState='hidden' can pause LinkedIn rendering
          2. IntersectionObserver — callbacks are skipped / delayed for off-screen tabs,
                                    which is exactly what LinkedIn uses to lazy-load cards
          3. hasFocus / mousemove — some render paths gate on document focus

        This method overrides all three at runtime, after the page has loaded.
        The guard flag (_focusPatched) prevents double-patching on re-injection.
        """
        self.driver.execute_script("""
            if (window._focusPatched) return;
            window._focusPatched = true;

            // ── 1. Page Visibility API ────────────────────────────────────────
            // Make the page believe it is always visible so LinkedIn never pauses
            // its rendering pipeline due to tab visibility.
            try {
                Object.defineProperty(document, 'visibilityState', {
                    get: function() { return 'visible'; },
                    configurable: true
                });
                Object.defineProperty(document, 'hidden', {
                    get: function() { return false; },
                    configurable: true
                });
                document.dispatchEvent(new Event('visibilitychange'));
            } catch(e) {}

            // ── 2. IntersectionObserver ───────────────────────────────────────
            // LinkedIn lazy-loads job cards using IntersectionObserver: a card
            // only renders when the browser reports it has entered the viewport.
            // In a background tab Chrome never fires those callbacks, so cards
            // never render.  We wrap observe() to immediately fire the callback
            // with isIntersecting=true for every element that is registered,
            // forcing all lazy-loaded content to render up-front.
            if (window.IntersectionObserver) {
                var _OrigIO = window.IntersectionObserver;
                window.IntersectionObserver = function(callback, options) {
                    var io = new _OrigIO(callback, options);
                    var _origObserve = io.observe.bind(io);
                    io.observe = function(target) {
                        _origObserve(target);
                        try {
                            var rect = target.getBoundingClientRect();
                            var rootRect = document.documentElement.getBoundingClientRect();
                            callback([{
                                isIntersecting: true,
                                intersectionRatio: 1.0,
                                target: target,
                                boundingClientRect: rect,
                                intersectionRect: rect,
                                rootBounds: rootRect,
                                time: performance.now()
                            }], io);
                        } catch(e) {}
                    };
                    return io;
                };
                window.IntersectionObserver.prototype = _OrigIO.prototype;
            }

            // ── 3. Focus signals ─────────────────────────────────────────────
            try { window.focus(); } catch(e) {}
            try {
                document.dispatchEvent(
                    new MouseEvent('mousemove', {bubbles: true, cancelable: true,
                                                clientX: 600, clientY: 400})
                );
            } catch(e) {}
        """)

    def _scroll_job_list_panel(self, max_attempts: int = 25, pause: float = 1.5):
        """
        Scroll the LEFT job-list panel until all cards are loaded.
        LinkedIn lazy-loads cards as you scroll, so scrollHeight grows with each batch.
        We keep scrolling to the current bottom until scrollHeight stops changing.
        """
        panel_selectors = [
            "div.scaffold-layout__list",
            "div.jobs-search-results-list",
            "div.jobs-search__results-list",
            "ul.scaffold-layout__list-container",
        ]

        panel = None
        for sel in panel_selectors:
            try:
                panel = self.driver.find_element(By.CSS_SELECTOR, sel)
                logger.debug(f"Job list panel found: {sel}")
                break
            except Exception:
                continue

        if panel is None:
            logger.warning("Job list panel not found — falling back to window scroll")
            scroll_page(self.driver)
            return

        prev_height = -1
        for i in range(max_attempts):
            # Scroll all the way to the current bottom
            self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", panel)
            time.sleep(pause)

            new_height = self.driver.execute_script("return arguments[0].scrollHeight", panel)
            logger.debug(f"Scroll attempt {i + 1}: scrollHeight={new_height}")

            if new_height == prev_height:
                logger.debug(f"Panel height stabilized at {new_height}px after {i + 1} scrolls")
                break
            prev_height = new_height

        time.sleep(1)  # Final wait for last batch of cards to render

    def _wait_for_jobs_list(self, timeout: int = 20) -> bool:
        """Wait until any job card element appears on the page."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, WAIT_SELECTORS)
                )
            )
            return True
        except Exception:
            return False

    def _parse_job_cards(self, soup: BeautifulSoup) -> list:
        """Try many CSS selectors to find job cards — logged-in and public."""
        for selector in CARD_CSS_SELECTORS:
            cards = soup.select(selector)
            if cards:
                logger.info(f"✓ Found {len(cards)} cards with: {selector}")
                return cards

        # Absolute last resort — find anything with a job link
        logger.warning("No cards found with standard selectors — trying link-based fallback")
        job_links = soup.select("a[href*='/jobs/view/']")
        if job_links:
            # Return parent elements as "cards"
            cards = []
            for link in job_links:
                parent = link.find_parent("li") or link.find_parent("div")
                if parent and parent not in cards:
                    cards.append(parent)
            if cards:
                logger.info(f"✓ Found {len(cards)} cards via link-based fallback")
                return cards

        return []

    def _extract_link(self, card) -> str | None:
        """Extract job link from a card using multiple strategies."""
        # Strategy 1: CSS selectors for known link classes
        for selector in LINK_SELECTORS:
            link_tag = card.select_one(selector)
            if link_tag and link_tag.get("href"):
                href = link_tag["href"].split("?")[0]
                if "/jobs/" in href:
                    if href.startswith("/"):
                        href = "https://www.linkedin.com" + href
                    return href

        # Strategy 2: ANY <a> tag with /jobs/ in the href
        for a_tag in card.find_all("a", href=True):
            href = a_tag["href"].split("?")[0]
            if "/jobs/" in href:
                if href.startswith("/"):
                    href = "https://www.linkedin.com" + href
                return href

        # Strategy 3: data-job-id attribute → construct link manually
        job_id = card.get("data-job-id")
        if not job_id:
            # Check children for data-job-id
            child = card.find(attrs={"data-job-id": True})
            if child:
                job_id = child["data-job-id"]
        if job_id:
            return f"https://www.linkedin.com/jobs/view/{job_id}"

        # Strategy 4: Extract job ID from any attribute or onclick
        card_html = str(card)
        import re
        job_id_match = re.search(r'/jobs/view/(\d+)', card_html)
        if job_id_match:
            return f"https://www.linkedin.com/jobs/view/{job_id_match.group(1)}"

        return None

    def _scrape_single_page(self, keyword: str, url: str, page_num: int, location: str = "") -> list[dict] | None:
        """Scrape a single page of LinkedIn job results."""
        logger.info(f"  Page {page_num}: {url}")

        try:
            self.driver.get(url)
        except Exception as e:
            logger.error(f"driver.get() failed: {e}")
            return None

        random_sleep(5, 7)
        logger.info(f"  Page {page_num} loaded. Title: {self.driver.title}")

        # Warn when LinkedIn auto-selects a job (appends currentJobId to URL).
        # This opens the right-side description panel — the panel finder below
        # explicitly excludes it, but logging helps confirm the fix is working.
        current_url = self.driver.current_url
        if "currentJobId" in current_url:
            logger.debug(f"  currentJobId detected in URL — right panel open, left panel will be targeted")

        # --- Detect page state ---
        state = _detect_page_state(self.driver)

        if state == "login_wall":
            logger.warning("Login wall detected — waiting 5s and retrying...")
            time.sleep(5)
            self.driver.get(url)
            time.sleep(5)
            state = _detect_page_state(self.driver)
            if state == "login_wall":
                _save_screenshot(self.driver, f"login_wall_{keyword.replace(' ', '_')}_p{page_num}")
                return None

        if state == "captcha":
            logger.error("CAPTCHA detected! Manual intervention needed.")
            _save_screenshot(self.driver, "captcha_detected")
            input(">>> Solve the CAPTCHA in the browser, then press ENTER to continue...")
            state = _detect_page_state(self.driver)

        if state not in ("jobs", "unknown"):
            logger.warning(f"Unexpected page state '{state}', skipping page...")
            return None

        # --- Wait for job cards ---
        jobs_loaded = self._wait_for_jobs_list(timeout=20)
        if not jobs_loaded:
            logger.info(f"  Page {page_num}: No jobs loaded (end of results)")
            return None

        # Patch the page so lazy loading works regardless of tab focus.
        # Called after the initial job list is confirmed present so the
        # IntersectionObserver override catches observers registered on load.
        self._inject_focus_overrides()

        # ── Scroll + collect links incrementally (handles LinkedIn's virtual list) ──
        # LinkedIn only renders visible cards in the DOM at any moment.
        # We collect links at each scroll step so we accumulate all of them.
        import re as _re
        results = []
        duplicate_count = 0
        blocked_count = 0
        reposted_count = 0
        high_applicant_count = 0

        # Find the scrollable job-list (LEFT) panel.
        #
        # Root cause of the bug: when LinkedIn auto-selects a job it appends
        # ?currentJobId=… to the URL and renders the full job description in the
        # RIGHT panel.  That detail panel is also scrollable and contains
        # a[href*='/jobs/view/'] links (related jobs, back-link, etc.), so the
        # old "pick smallest scrollable container" heuristic could choose it instead
        # of the left list panel.
        #
        # Fix — two-step strategy:
        #   1. Try well-known left-panel CSS selectors first (fast, reliable when present).
        #   2. Fall back to the heuristic, but explicitly exclude anything inside
        #      the right-side detail/description container.

        # Step 1: named left-panel selectors
        panel = self.driver.execute_script("""
            var sels = [
                'div.scaffold-layout__list',
                'div.jobs-search-results-list',
                'div.jobs-search__results-list',
                'ul.scaffold-layout__list-container',
                'div.scaffold-layout__list-container'
            ];
            for (var i = 0; i < sels.length; i++) {
                var el = document.querySelector(sels[i]);
                if (el && el.scrollHeight > el.clientHeight + 50) return el;
            }
            return null;
        """)

        if not panel:
            # Step 2: heuristic fallback — smallest scrollable container that has job
            # links, but never pick anything inside the right-side detail panel.
            panel = self.driver.execute_script("""
                var detailSels = [
                    '.scaffold-layout__detail',
                    '.jobs-search__job-details',
                    '.job-view-layout',
                    '.jobs-details',
                    '.jobs-unified-top-card'
                ];
                var best = null, bestSize = Infinity;
                document.querySelectorAll('div, ul, section').forEach(function(el) {
                    for (var d = 0; d < detailSels.length; d++) {
                        if (el.closest(detailSels[d])) return;
                    }
                    var oy = window.getComputedStyle(el).overflowY;
                    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 50) {
                        if (el.querySelector("a[href*='/jobs/view/']")) {
                            if (el.scrollHeight < bestSize) {
                                bestSize = el.scrollHeight;
                                best = el;
                            }
                        }
                    }
                });
                return best;
            """)

        if panel:
            panel_height = self.driver.execute_script("return arguments[0].scrollHeight", panel)
            logger.info(f"  Job list panel found (scrollHeight={panel_height}px)")
        else:
            logger.warning("  Job list panel NOT found — falling back to window scroll")

        seen_ids_this_page: dict[str, object] = {}  # job_id → anchor element
        no_new_streak = 0

        for _step in range(60):  # max 60 steps × 300px ≈ 18 000px
            # Collect all currently visible job links
            try:
                _anchors = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            except Exception:
                _anchors = []

            _new_this_step = 0
            for _anchor in _anchors:
                _href = _anchor.get_attribute("href") or ""
                _m = _re.search(r"/jobs/view/(\d+)", _href)
                if _m:
                    _jid = _m.group(1)
                    if _jid not in seen_ids_this_page:
                        # Capture card HTML now while element is still in DOM
                        try:
                            _card_html = self.driver.execute_script(
                                """
                                var el = arguments[0];
                                var card = el.closest('li') || el.closest('div.job-card-container') || el.parentElement;
                                return card ? card.outerHTML : el.outerHTML;
                                """,
                                _anchor,
                            )
                        except Exception:
                            _card_html = f'<div data-job-id="{_jid}"></div>'
                        seen_ids_this_page[_jid] = _card_html  # store HTML, not anchor
                        _new_this_step += 1

            # Scroll down to reveal next batch of cards.
            # After every scroll we explicitly dispatch 'scroll' events so
            # LinkedIn's scroll listeners and IntersectionObserver triggers
            # fire even when the tab is not in the foreground.
            if panel:
                self.driver.execute_script(
                    """
                    arguments[0].scrollTop += 600;
                    arguments[0].dispatchEvent(new Event('scroll', {bubbles: true}));
                    window.dispatchEvent(new Event('scroll'));
                    """,
                    panel,
                )
            elif _anchors:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'start'})",
                        _anchors[-1],
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
            time.sleep(2.0)

            if _new_this_step == 0:
                no_new_streak += 1
                if no_new_streak >= 5:
                    logger.info(f"  No new links for 5 steps — scroll complete at step {_step + 1}")
                    break
            else:
                no_new_streak = 0

        logger.info(f"  Page {page_num}: {len(seen_ids_this_page)} unique job links in DOM")

        if not seen_ids_this_page:
            # Scroll ran but found zero job links → genuine end of results for this keyword
            return None

        for job_id, card_html in seen_ids_this_page.items():
            href = f"https://www.linkedin.com/jobs/view/{job_id}"

            # Global dedup
            if href in self.seen_links:
                duplicate_count += 1
                continue

            # Skip reposted jobs
            if card_html and "reposted" in card_html.lower():
                logger.debug(f"  Skipping reposted job: {job_id}")
                reposted_count += 1
                continue

            # Skip jobs at or above the applicant threshold (0 = disabled)
            if card_html and _cfg.MAX_APPLICANTS > 0:
                _over_match = _re.search(r'over\s+(\d+)\s+applicants?', card_html, _re.IGNORECASE)
                _exact_match = _re.search(r'(\d+)\s+applicants?', card_html, _re.IGNORECASE)
                if _over_match:
                    logger.debug(f"  Skipping high-applicant job (over {_over_match.group(1)}): {job_id}")
                    high_applicant_count += 1
                    continue
                elif _exact_match:
                    _count = int(_exact_match.group(1))
                    if _count >= _cfg.MAX_APPLICANTS:
                        logger.debug(f"  Skipping {_count}-applicant job (threshold={_cfg.MAX_APPLICANTS}): {job_id}")
                        high_applicant_count += 1
                        continue

            # Pre-filter: check company name in card HTML.
            # Normalise spaces so "RemoteHunter" matches "remote hunter".
            card_text_lower = card_html.lower() if card_html else ""
            card_text_nospace = card_text_lower.replace(" ", "")
            company_blocked = False
            for blocked in _cfg.EXCLUDED_COMPANIES:
                if blocked.lower() in card_text_lower or blocked.lower().replace(" ", "") in card_text_nospace:
                    logger.debug(f"  Pre-filter blocked company in card: '{blocked}'")
                    blocked_count += 1
                    company_blocked = True
                    break
            if company_blocked:
                continue

            self.seen_links.add(href)
            results.append({"html": card_html, "link": href, "description": None})

        logger.info(
            f"  Page {page_num}: {len(results)} new | "
            f"{duplicate_count} dupes | "
            f"{blocked_count} blocked | "
            f"{reposted_count} reposted | "
            f"{high_applicant_count} 100+ applicants"
        )

        # Fetch descriptions + follower/employee counts from the right panel.
        if results:
            panel_data = self._fetch_descriptions_from_panel(results)
            for r in results:
                entry = panel_data.get(r["link"]) or {}
                r["description"] = entry.get("description")
                r["linkedin_followers"] = entry.get("linkedin_followers")
                r["linkedin_employees"] = entry.get("linkedin_employees")
        return results

    def _fetch_descriptions_from_panel(self, cards: list[dict]) -> dict:
        """Click each job card, extract description + follower count from right panel.

        Returns dict of link -> {"description": str|None, "linkedin_followers": int|None}.
        """
        import re as _re2
        results = {}

        _JS_HTML = """
        var p = document.querySelector('.scaffold-layout__detail') ||
                document.querySelector('.jobs-search__job-details');
        return p ? p.innerHTML : null;
        """

        for card in cards:
            link = card["link"]
            m = _re2.search(r"/jobs/view/(\d+)", link)
            if not m:
                continue
            job_id = m.group(1)

            # Bail out if LinkedIn redirected to a login/captcha page mid-session
            current_url = self.driver.current_url
            if any(x in current_url for x in ("login", "authwall", "checkpoint", "captcha")):
                logger.warning("  Session interrupted (login/captcha) — stopping description fetch")
                break

            try:
                clicked = self.driver.execute_script(f"""
                    var el = document.querySelector('[data-job-id="{job_id}"]') ||
                             document.querySelector('a[href*="/jobs/view/{job_id}"]');
                    if (el) {{ el.click(); return true; }}
                    return false;
                """)
                if not clicked:
                    logger.debug(f"  Right-panel click: card not found in DOM for {job_id}")
                    continue

                time.sleep(2.0)

                try:
                    panel_els = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        ".scaffold-layout__detail, .jobs-search__job-details",
                    )
                    if panel_els:
                        origin = ScrollOrigin.from_element(panel_els[0])
                        ActionChains(self.driver).scroll_from_origin(origin, 0, 400).perform()
                        time.sleep(0.8)
                        ActionChains(self.driver).scroll_from_origin(origin, 0, 500).perform()
                        time.sleep(1.0)
                except Exception as e:
                    logger.debug(f"  Right-panel scroll failed: {e}")

                panel_html = self.driver.execute_script(_JS_HTML)
                text = self._extract_description_from_html(panel_html, job_id)
                followers = self._extract_followers_from_html(panel_html)
                employees = self._extract_employee_count_from_html(panel_html)

                if text and len(text) > 100:
                    logger.debug(f"  Right-panel description: {job_id} ({len(text)} chars)")
                else:
                    text = None
                    logger.debug(f"  Right-panel: no description for {job_id}")
                    self._save_panel_debug_html(job_id)

                results[link] = {
                    "description": text,
                    "linkedin_followers": followers,
                    "linkedin_employees": employees,
                }

            except Exception as e:
                logger.debug(f"  Right-panel description failed for {job_id}: {e}")

            time.sleep(random.uniform(0.5, 1.0))

        found = sum(1 for v in results.values() if v.get("description"))
        logger.info(f"  Descriptions fetched from right panel: {found}/{len(cards)}")
        return results

    def _extract_followers_from_html(self, panel_html: str | None) -> int | None:
        """Extract LinkedIn company follower count from the right-panel HTML."""
        import re as _re4
        if not panel_html:
            return None
        text = BeautifulSoup(panel_html, "html.parser").get_text(" ", strip=True)
        m = _re4.search(r"([\d,]+(?:\.\d+)?)\s*(K)?\s*followers", text, _re4.IGNORECASE)
        if not m:
            return None
        try:
            value = float(m.group(1).replace(",", ""))
            if m.group(2):
                value *= 1000
            return int(value)
        except ValueError:
            return None

    def _extract_employee_count_from_html(self, panel_html: str | None) -> int | None:
        """Extract employee count from LinkedIn right-panel company section.

        LinkedIn shows ranges like '10,001+ employees' or '1,001-5,000 employees'.
        Returns the lower bound of the range as an integer.
        """
        import re as _re5
        if not panel_html:
            return None
        text = BeautifulSoup(panel_html, "html.parser").get_text(" ", strip=True)
        # Match: "10,001+ employees"  or  "1,001-5,000 employees"
        m = _re5.search(r"([\d,]+)\+?\s*(?:-[\d,]+)?\s*employees", text, _re5.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None

    def _extract_description_from_html(self, panel_html: str | None, job_id: str) -> str | None:
        """Parse raw panel innerHTML with BeautifulSoup and return description text.

        Tries in order:
          1. Element with id="job-details" (stable LinkedIn ID seen in live DOM)
          2. "About the job" / "About this role" heading → walk up to container
          3. Any element whose class contains "jobs-box__html-content"
        Returns None if nothing substantial (>100 chars) is found.
        """
        import re as _re3
        if not panel_html:
            return None
        soup = BeautifulSoup(panel_html, "html.parser")

        # 1. Stable ID — confirmed present in debug HTML captures
        el = soup.find(id="job-details")
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text

        # 2. "About the job" heading → walk up until we have a meaty block
        for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
            if _re3.search(r"about the job|about this role|job description", heading.get_text(), _re3.I):
                node = heading.parent
                for _ in range(6):
                    if node is None:
                        break
                    candidate = node.get_text(separator="\n", strip=True)
                    if len(candidate) > 300:
                        return candidate
                    node = node.parent

        # 3. jobs-box__html-content class (observed in live DOM)
        el = soup.find(class_=lambda c: c and "jobs-box__html-content" in " ".join(c))
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text

        return None

    def _save_panel_debug_html(self, job_id: str):
        """Save the right-panel innerHTML so failing selectors can be inspected."""
        import os
        debug_dir = os.path.join(os.path.dirname(__file__), "..", "logs", "debug_screenshots")
        try:
            os.makedirs(debug_dir, exist_ok=True)
            html = self.driver.execute_script("""
                var p = document.querySelector('.scaffold-layout__detail') ||
                        document.querySelector('.jobs-search__job-details');
                return p ? p.innerHTML : document.body.innerHTML;
            """)
            path = os.path.join(debug_dir, f"panel_{job_id}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html or "")
            logger.debug(f"  Panel debug HTML saved: {path}")
        except Exception as e:
            logger.debug(f"  Could not save panel debug HTML: {e}")

    def search_jobs(
        self,
        keyword: str,
        max_results: int = None,
        process_batch=None,
        location: str = "",
    ) -> list[dict]:
        """Scrape multiple pages of results for a keyword (up to max_results).

        Args:
            process_batch: optional callable(cards: list[dict]) invoked immediately
                           after each page is scraped, enabling real-time DB insertion.
            location: LinkedIn location string (e.g. "United States"). Empty = global.
        """
        if max_results is None:
            max_results = _cfg.MAX_RESULTS_PER_SKILL
        per_page = 25
        total_pages = max_results // per_page
        loc_label = f" in [{location}]" if location else " [global]"
        logger.info(f"━━━ Searching: [{keyword}]{loc_label} — up to {max_results} jobs ({total_pages} pages) ━━━")

        all_results = []

        for page_num in range(1, total_pages + 1):
            start = (page_num - 1) * per_page
            url = build_search_url(keyword, start=start, location=location)

            page_results = self._scrape_single_page(keyword, url, page_num, location=location)

            if page_results is None:
                # Page had zero jobs in the DOM — genuine end of results for this keyword
                logger.info(f"  No more results after page {page_num} — stopping early")
                break

            # page_results == [] means the page had jobs but all were already seen
            # in a previous skill's run — keep paginating, do NOT break
            if page_results:
                # Real-time processing: insert this page's cards before moving on
                if process_batch:
                    process_batch(page_results)
                all_results.extend(page_results)

            logger.info(f"  [{keyword}] running total: {len(all_results)} unique jobs")

            if page_num < total_pages:
                random_sleep(3, 5)

        logger.info(f"━━━ [{keyword}] done: {len(all_results)} unique jobs ━━━")
        return all_results

    def scrape_all_skills(
        self,
        process_batch=None,
        on_keyword_done=None,
        countries: list[str] | None = None,
    ) -> list[dict]:
        """Search all skill keywords + job title queries across all countries, deduplicated.

        Args:
            process_batch:    optional callable(cards) invoked after each page.
            on_keyword_done:  optional callable(keyword, cards_scraped) invoked once
                              per (term, country) pair after all its pages finish.
            countries:        list of LinkedIn location strings. Defaults to SEARCH_COUNTRIES.
                              Pass [""] for a global (no-location-filter) search.
        """
        if countries is None:
            countries = _cfg.SEARCH_COUNTRIES

        all_jobs = []
        total_terms = len(_cfg.ALL_SEARCH_TERMS)
        total_combos = total_terms * len(countries)
        combo_idx = 0

        for country in countries:
            loc_label = country if country else "global"
            logger.info(f"{'━' * 60}")
            logger.info(f"  Location: {loc_label}  |  {total_terms} search terms")
            logger.info(f"{'━' * 60}")

            for idx, term in enumerate(_cfg.ALL_SEARCH_TERMS, 1):
                combo_idx += 1
                logger.info(f"[{combo_idx}/{total_combos}] [{loc_label}] {term}")
                try:
                    jobs = self.search_jobs(term, process_batch=process_batch, location=country)
                    all_jobs.extend(jobs)

                    if on_keyword_done:
                        on_keyword_done(f"{term} [{loc_label}]", len(jobs))

                    random_sleep() if jobs else random_sleep(2, 4)
                except Exception as e:
                    logger.error(f"Failed to scrape '{term}' in '{loc_label}': {e}")
                    continue

        logger.info(f"━━━ TOTAL unique jobs scraped across all terms/countries: {len(all_jobs)} ━━━")
        return all_jobs
