import time
import random
from urllib.parse import quote_plus

from selenium.webdriver.remote.webdriver import WebDriver

import config.settings as _cfg


def random_sleep(min_s: int = None, max_s: int = None):
    if min_s is None:
        min_s = _cfg.MIN_DELAY
    if max_s is None:
        max_s = _cfg.MAX_DELAY
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)


def build_search_url(keyword: str, start: int = 0, location: str = "") -> str:
    encoded = quote_plus(keyword)
    url = f"{_cfg.LINKEDIN_BASE_URL}?keywords={encoded}&f_TPR={_cfg.TIME_FILTER}&start={start}"
    if location:
        url += f"&location={quote_plus(location)}"
    return url


def scroll_page(driver: WebDriver, pause: int = None, max_scrolls: int = None):
    if pause is None:
        pause = _cfg.SCROLL_PAUSE
    if max_scrolls is None:
        max_scrolls = _cfg.MAX_SCROLLS

    from loguru import logger

    last_height = driver.execute_script("return document.body.scrollHeight")

    for i in range(max_scrolls):
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(pause)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            # Try clicking "See more jobs" / "Show more" buttons (logged-in view)
            clicked = False
            more_buttons = [
                "button.infinite-scroller__show-more-button",
                "button.jobs-search-results-list__load-more",
                "button[aria-label='See more jobs']",
                "button.scaffold-finite-scroll__load-button",
            ]
            for btn_sel in more_buttons:
                try:
                    btn = driver.find_element("css selector", btn_sel)
                    btn.click()
                    logger.debug(f"Clicked 'load more' button: {btn_sel}")
                    time.sleep(pause + 1)
                    clicked = True
                    break
                except Exception:
                    pass
            if not clicked:
                logger.debug(f"Scroll ended after {i + 1} scrolls (no more content)")
                break
        last_height = new_height
