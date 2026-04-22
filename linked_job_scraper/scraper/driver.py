import os
import subprocess
import winreg
import undetected_chromedriver as uc
from selenium_stealth import stealth
from loguru import logger


def _get_chrome_version() -> int | None:
    """Detect installed Chrome major version on Windows via multiple methods."""

    # Method 1: Windows Registry (most reliable)
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon"),
    ]
    for hive, key_path in reg_paths:
        try:
            key = winreg.OpenKey(hive, key_path)
            version_str, _ = winreg.QueryValueEx(key, "version")
            winreg.CloseKey(key)
            major = int(version_str.split(".")[0])
            logger.info(f"Chrome version from registry: {version_str} (major={major})")
            return major
        except (OSError, FileNotFoundError, ValueError):
            continue

    # Method 2: PowerShell file version
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for chrome_path in chrome_paths:
        if os.path.exists(chrome_path):
            try:
                result = subprocess.run(
                    ["powershell", "-Command",
                     f"(Get-Item '{chrome_path}').VersionInfo.FileVersion"],
                    capture_output=True, text=True, timeout=10,
                )
                version_str = result.stdout.strip()
                if version_str:
                    major = int(version_str.split(".")[0])
                    logger.info(f"Chrome version from PowerShell: {version_str} (major={major})")
                    return major
            except Exception:
                continue

    logger.warning("Could not auto-detect Chrome version")
    return None


def _build_options() -> uc.ChromeOptions:
    """Always build a fresh ChromeOptions — never reuse the same object."""
    opts = uc.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--log-level=3")
    opts.add_argument("--silent")
    # ── Background-tab throttling fixes ──────────────────────────────────────
    # Chrome heavily throttles tabs that are not in the foreground:
    # timers are slowed, IntersectionObserver callbacks are delayed, and
    # rendering budgets are cut.  These flags disable that behaviour so the
    # scraper extracts the same number of cards whether the tab is focused or not.
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-background-media-suspend")
    return opts


def create_driver() -> uc.Chrome:
    logger.info("Initializing Chrome driver with stealth settings...")

    version = _get_chrome_version()

    if version is None:
        # Hardcode fallback based on known error output
        version = 146
        logger.warning(f"Using hardcoded Chrome version fallback: {version}")

    logger.info(f"Launching Chrome with version_main={version}")

    driver = uc.Chrome(
        options=_build_options(),
        version_main=version,
        use_subprocess=True,
        headless=False,
    )

    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    logger.info("Chrome driver ready.")
    return driver
