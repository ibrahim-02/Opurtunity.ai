"""
Scrape the full job description from a LinkedIn job detail page.

Usage:
    from scraper.detail_scraper import scrape_description

    text = scrape_description(driver, "https://www.linkedin.com/jobs/view/1234567890")
    # Returns the description string, or None if unavailable / expired.
"""
import time

from bs4 import BeautifulSoup
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scraper.utils import random_sleep

# Phrases that indicate the job is gone.
_EXPIRED_PHRASES = [
    "no longer available",
    "job has been closed",
    "this job has expired",
    "job is no longer accepting",
]

# "See more" / "Show more" buttons — tried by aria-label, not class name.
_SEE_MORE_ARIA = [
    "Click to see more description",
    "see more",
    "Show more",
]

# JS with 4-strategy fallback. Uses textContent as fallback for innerText because
# innerText returns '' for elements that CSS hides (display:none / overflow:hidden).
_JS_EXTRACT = """
(function() {
    // Lift CSS truncation from all known description wrapper classes.
    if (!document.getElementById('_lj_fix')) {
        var s = document.createElement('style');
        s.id = '_lj_fix';
        s.textContent = '[class*="show-more-less-html"], [class*="jobs-box__html-content"], [class*="jobs-description-content__text"] { max-height: none !important; overflow: visible !important; -webkit-line-clamp: unset !important; display: block !important; }';
        document.head.appendChild(s);
    }

    function getText(el) {
        if (!el) return '';
        return ((el.innerText || el.textContent) || '').trim();
    }

    // Strategy 0: #job-details — stable LinkedIn element ID seen in live DOM captures.
    var byId = document.getElementById('job-details');
    if (byId) {
        var t = getText(byId);
        if (t.length > 100) return t;
    }

    // Strategy 1: show-more-less-html markup
    var els = document.querySelectorAll('[class*="show-more-less-html__markup"]');
    for (var i = 0; i < els.length; i++) {
        var t = getText(els[i]);
        if (t.length > 100) return t;
    }

    // Strategy 2: jobs-description / jobs-box content containers
    var desc = document.querySelector('[class*="jobs-box__html-content"]') ||
               document.querySelector('[class*="jobs-description__content"]') ||
               document.querySelector('[class*="jobs-description-content"]');
    if (desc) {
        var t = getText(desc);
        if (t.length > 100) return t;
    }

    // Strategy 3: heading-based (case-insensitive, partial match)
    var headings = document.querySelectorAll('h2, h3, h4, strong');
    for (var i = 0; i < headings.length; i++) {
        var ht = (headings[i].textContent || '').trim();
        if (/about the job|about this role|job description/i.test(ht)) {
            var node = headings[i].parentElement;
            for (var j = 0; j < 8; j++) {
                if (!node) break;
                var t = getText(node);
                if (t.length > 300) return t;
                node = node.parentElement;
            }
        }
    }

    return null;
})()
"""

# Fallback wait selector — broad enough to survive LinkedIn class obfuscation.
_WAIT_SELECTOR = "main"


# ── Public API ────────────────────────────────────────────────────────────────

def scrape_description(driver: WebDriver, url: str, timeout: int = 15) -> str | None:
    """Navigate to *url* and return the job description text.

    Returns None when:
    - the job is expired / removed
    - a login wall or CAPTCHA blocks the page
    - the description container is not found within *timeout* seconds
    """
    logger.debug(f"Detail page: {url}")

    try:
        driver.get(url)
    except Exception as e:
        logger.warning(f"driver.get() failed for {url}: {e}")
        return None

    # Brief pause so the page starts loading before we inspect state.
    time.sleep(2)

    state = _detect_state(driver)

    if state == "login_wall":
        logger.warning(f"Login wall on detail page: {url}")
        return None

    if state == "captcha":
        logger.warning("CAPTCHA on detail page — skipping")
        return None

    if state == "expired":
        logger.debug(f"Job expired/removed: {url}")
        return None

    # Wait for the main content to appear.
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, _WAIT_SELECTOR))
        )
    except Exception:
        logger.debug(f"Page did not load within {timeout}s: {url}")
        _save_debug_html(driver, url)
        return None

    # Click "See more" if present so we get the full text.
    _expand_description(driver)

    return _extract_text(driver, url)


# ── Internals ─────────────────────────────────────────────────────────────────

def _detect_state(driver: WebDriver) -> str:
    url = driver.current_url.lower()
    if "checkpoint" in url or "captcha" in url:
        return "captcha"
    if "login" in url or "authwall" in url or "uas/login" in url:
        return "login_wall"

    page_text = driver.page_source.lower()
    if any(phrase in page_text for phrase in _EXPIRED_PHRASES):
        return "expired"

    return "ok"


def _expand_description(driver: WebDriver):
    """Scroll to the description area and click the 'See more' button via JS.

    Uses JS click so the button doesn't need to be in the viewport — LinkedIn
    truncates descriptions with CSS (overflow:hidden) and the button can be
    off-screen until the page is scrolled.
    """
    try:
        clicked = driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var label = (btns[i].getAttribute('aria-label') || btns[i].textContent || '').toLowerCase();
                if (label.indexOf('see more') !== -1 || label.indexOf('show more') !== -1) {
                    btns[i].scrollIntoView({block: 'center'});
                    btns[i].click();
                    return true;
                }
            }
            return false;
        """)
        if clicked:
            time.sleep(1)
    except Exception:
        pass


def _extract_text(driver: WebDriver, url: str) -> str | None:
    # Primary: JavaScript content-based extraction (stable against class obfuscation)
    try:
        text = driver.execute_script(_JS_EXTRACT)
        if text and len(text) > 100:
            logger.debug(f"Description extracted via JS ({len(text)} chars): {url}")
            return text.strip()
    except Exception as e:
        logger.debug(f"JS extraction failed: {e}")

    # Fallback: BeautifulSoup content-based extraction
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # BS4 fallback 1: show-more-less-html markup (substring class match)
    for tag in soup.find_all(True, class_=lambda c: c and "show-more-less-html__markup" in " ".join(c)):
        text = tag.get_text(separator="\n", strip=True)
        if len(text) > 100:
            logger.debug(f"Description via BS4 show-more-less ({len(text)} chars): {url}")
            return text

    # BS4 fallback 2: jobs-description content containers
    for cls_frag in ("jobs-description__content", "jobs-description-content", "jobs-box__html-content"):
        tag = soup.find(True, class_=lambda c: c and cls_frag in " ".join(c))
        if tag:
            text = tag.get_text(separator="\n", strip=True)
            if len(text) > 100:
                logger.debug(f"Description via BS4 {cls_frag} ({len(text)} chars): {url}")
                return text

    # BS4 fallback 3: heading-based (case-insensitive, partial)
    import re as _re
    heading = soup.find(
        ["h2", "h3", "h4", "strong"],
        string=lambda t: t and _re.search(r"about the job|about this role|job description", t, _re.I),
    )
    if heading:
        node = heading.parent
        for _ in range(8):
            if not node:
                break
            text = node.get_text(separator="\n", strip=True)
            if len(text) > 300:
                logger.debug(f"Description extracted via BS4 heading ({len(text)} chars): {url}")
                return text
            node = node.parent

    logger.debug(f"No description found: {url}")
    _save_debug_html(driver, url)
    return None


def _save_debug_html(driver: WebDriver, url: str):
    """Save page source so we can inspect failing selectors later."""
    import os
    import re
    debug_dir = os.path.join(os.path.dirname(__file__), "..", "logs", "debug_screenshots")
    try:
        os.makedirs(debug_dir, exist_ok=True)
        job_id = re.search(r"/jobs/view/(\d+)", url)
        name = f"detail_{job_id.group(1) if job_id else 'unknown'}.html"
        path = os.path.join(debug_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.debug(f"Debug HTML saved: {path}")
    except Exception as e:
        logger.warning(f"Could not save debug HTML: {e}")
