"""
Browser automation — Playwright-based, with CDP fallback.
"""

import base64
import io
from dataclasses import dataclass
from typing import Optional


@dataclass
class BrowserState:
    url: str = ""
    title: str = ""
    screenshot_png: bytes = b""


class Browser:
    """Cross-browser automation via Playwright."""

    def __init__(self, headless: bool = False, browser_type: str = "chromium") -> None:
        self._headless = headless
        self._browser_type = browser_type
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_playwright(self) -> None:
        if self._playwright is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise RuntimeError(
                    "Playwright not installed. Run: pip install playwright && playwright install"
                )
            self._playwright = sync_playwright().start()
            browser_cls = getattr(self._playwright, self._browser_type)
            self._browser = browser_cls.launch(headless=self._headless)
            self._page = self._browser.new_page()

    def launch(self, url: str) -> BrowserState:
        """Launch browser and navigate to URL."""
        self._ensure_playwright()
        self._page.goto(url, wait_until="domcontentloaded")
        return self._get_state()

    def goto(self, url: str) -> BrowserState:
        self._page.goto(url, wait_until="domcontentloaded")
        return self._get_state()

    def click(self, selector: str) -> BrowserState:
        self._page.click(selector)
        self._page.wait_for_timeout(300)
        return self._get_state()

    def type_text(self, selector: str, text: str) -> BrowserState:
        self._page.fill(selector, text)
        return self._get_state()

    def screenshot(self, fullpage: bool = False) -> bytes:
        return self._page.screenshot(full_page=fullpage)

    def get_text(self, selector: str) -> str:
        return self._page.text_content(selector) or ""

    def eval(self, js: str) -> str:
        result = self._page.evaluate(js)
        return str(result) if result is not None else ""

    def wait(self, selector: str, timeout_sec: float = 10.0) -> None:
        self._page.wait_for_selector(selector, timeout=int(timeout_sec * 1000))

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._page = None

    @property
    def page(self):
        return self._page

    def _get_state(self) -> BrowserState:
        png = self._page.screenshot()
        title = self._page.title()
        url = self._page.url
        return BrowserState(url=url, title=title, screenshot_png=png)


# ── Standalone functions ──

def browser_launch(url: str, headless: bool = False) -> dict:
    b = Browser(headless=headless)
    state = b.launch(url)
    return {
        "url": state.url,
        "title": state.title,
        "screenshot_b64": base64.b64encode(state.screenshot_png).decode(),
    }

def browser_close():
    pass  # Browser instances manage their own lifecycle
