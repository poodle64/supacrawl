"""Browser manager for Playwright-based page fetching."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

LOGGER = logging.getLogger(__name__)


@dataclass
class PageContent:
    """Result of fetching a page."""

    url: str
    html: str
    title: str | None
    status_code: int
    screenshot: bytes | None = None
    pdf: bytes | None = None


@dataclass
class PageMetadata:
    """Metadata extracted from a page (Firecrawl-compatible)."""

    # Core metadata
    title: str | None
    description: str | None
    language: str | None
    keywords: str | None
    robots: str | None
    canonical_url: str | None

    # OpenGraph metadata
    og_title: str | None
    og_description: str | None
    og_image: str | None
    og_url: str | None
    og_site_name: str | None


class BrowserManager:
    """Manages Playwright browser for page fetching.

    Usage:
        async with BrowserManager() as browser:
            content = await browser.fetch_page("https://example.com")
    """

    def __init__(
        self,
        headless: bool | None = None,
        timeout_ms: int | None = None,
        user_agent: str | None = None,
    ):
        """Initialize browser manager.

        Args:
            headless: Run headless (default from SUPACRAWL_HEADLESS env, or True)
            timeout_ms: Page load timeout (default from SUPACRAWL_TIMEOUT env, or 30000)
            user_agent: User agent string (default from SUPACRAWL_USER_AGENT env)
        """
        self.headless = (
            headless
            if headless is not None
            else self._env_bool("SUPACRAWL_HEADLESS", True)
        )
        self.timeout_ms = timeout_ms or int(os.getenv("SUPACRAWL_TIMEOUT", "30000"))
        self.user_agent = user_agent or os.getenv(
            "SUPACRAWL_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        self._browser: Browser | None = None
        self._playwright: Any = None

    @staticmethod
    def _env_bool(key: str, default: bool) -> bool:
        """Get boolean from environment variable."""
        val = os.getenv(key)
        if val is None:
            return default
        return val.strip().lower() in {"1", "true", "yes", "on"}

    async def __aenter__(self) -> "BrowserManager":
        """Start browser (async context manager entry)."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close browser (async context manager exit)."""
        await self.stop()

    async def start(self) -> None:
        """Start the browser.

        Can be called directly for manual lifecycle management, or implicitly
        via async context manager (async with BrowserManager() as browser).
        """
        if self._browser is not None:
            return  # Already started
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        LOGGER.debug("Browser started (headless=%s)", self.headless)

    async def stop(self) -> None:
        """Stop the browser and cleanup resources.

        Safe to call multiple times.
        """
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        LOGGER.debug("Browser stopped")

    async def fetch_page(
        self,
        url: str,
        wait_for_spa: bool = True,
        spa_timeout_ms: int = 5000,
        capture_screenshot: bool = False,
        capture_pdf: bool = False,
        screenshot_full_page: bool = True,
    ) -> PageContent:
        """Fetch a page with browser rendering.

        Args:
            url: URL to fetch
            wait_for_spa: Wait for SPA content to stabilize
            spa_timeout_ms: Max time to wait for SPA stability
            capture_screenshot: Capture PNG screenshot of page
            capture_pdf: Generate PDF of page
            screenshot_full_page: Capture full scrollable page (default True)

        Returns:
            PageContent with HTML, metadata, and optional screenshot/PDF

        Raises:
            RuntimeError: If browser not initialized or fetch fails
        """
        if not self._browser:
            raise RuntimeError(
                "Browser not initialized. Use 'async with BrowserManager()' context manager."
            )

        context: BrowserContext | None = None
        page: Page | None = None

        try:
            # Create fresh context for isolation
            locale = os.getenv("SUPACRAWL_LOCALE", "en-US")
            timezone = os.getenv("SUPACRAWL_TIMEZONE", "Australia/Brisbane")

            context = await self._browser.new_context(
                locale=locale,
                timezone_id=timezone,
                user_agent=self.user_agent,
            )

            page = await context.new_page()

            # Navigate to URL
            wait_until = os.getenv("SUPACRAWL_WAIT_UNTIL", "domcontentloaded")
            response = await page.goto(
                url, wait_until=wait_until, timeout=self.timeout_ms
            )

            # Wait for SPA stability if requested
            if wait_for_spa:
                await self._wait_for_spa_stability(page, spa_timeout_ms)

            # Additional fixed delay for any remaining JS execution
            await asyncio.sleep(0.5)

            # Extract HTML and title
            html = await page.content()
            title = await page.title() or None
            status_code = response.status if response else 200

            # Capture screenshot if requested
            screenshot_bytes: bytes | None = None
            if capture_screenshot:
                screenshot_bytes = await page.screenshot(
                    full_page=screenshot_full_page,
                    type="png",
                )

            # Generate PDF if requested (requires headless mode)
            pdf_bytes: bytes | None = None
            if capture_pdf:
                pdf_bytes = await page.pdf(
                    format="A4",
                    print_background=True,
                )

            return PageContent(
                url=url,
                html=html,
                title=title,
                status_code=status_code,
                screenshot=screenshot_bytes,
                pdf=pdf_bytes,
            )

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    async def extract_links(self, url: str) -> list[str]:
        """Extract all links from a rendered page.

        Args:
            url: URL to fetch and extract links from

        Returns:
            List of absolute URLs found on the page

        Raises:
            RuntimeError: If browser not initialized or fetch fails
        """
        if not self._browser:
            raise RuntimeError(
                "Browser not initialized. Use 'async with BrowserManager()' context manager."
            )

        context: BrowserContext | None = None
        page: Page | None = None

        try:
            # Create fresh context
            context = await self._browser.new_context(
                locale=os.getenv("SUPACRAWL_LOCALE", "en-US"),
                timezone_id=os.getenv("SUPACRAWL_TIMEZONE", "Australia/Brisbane"),
                user_agent=self.user_agent,
            )

            page = await context.new_page()

            # Navigate to URL
            wait_until = os.getenv("SUPACRAWL_WAIT_UNTIL", "domcontentloaded")
            await page.goto(url, wait_until=wait_until, timeout=self.timeout_ms)

            # Extract all links using JavaScript
            links = await page.evaluate(
                """
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    return anchors.map(a => a.href).filter(href => href && href.startsWith('http'));
                }
            """
            )

            return links

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    async def extract_metadata(self, html: str) -> PageMetadata:
        """Extract metadata from HTML (Firecrawl-compatible fields).

        Args:
            html: HTML content

        Returns:
            PageMetadata with title, description, og tags, and other metadata
        """
        soup = BeautifulSoup(html, "html.parser")

        def get_meta_content(name: str | None = None, property: str | None = None) -> str | None:
            """Helper to extract meta tag content."""
            if name:
                tag = soup.find("meta", attrs={"name": name})
            elif property:
                tag = soup.find("meta", attrs={"property": property})
            else:
                return None
            return tag.get("content", None) if tag else None

        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        # Extract core metadata
        description = get_meta_content(name="description")
        keywords = get_meta_content(name="keywords")
        robots = get_meta_content(name="robots")

        # Extract language from html tag
        html_tag = soup.find("html")
        language = html_tag.get("lang", None) if html_tag else None

        # Extract canonical URL
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        canonical_url = canonical_tag.get("href", None) if canonical_tag else None

        # Extract OpenGraph tags
        og_title = get_meta_content(property="og:title")
        og_description = get_meta_content(property="og:description")
        og_image = get_meta_content(property="og:image")
        og_url = get_meta_content(property="og:url")
        og_site_name = get_meta_content(property="og:site_name")

        return PageMetadata(
            title=title,
            description=description,
            language=language,
            keywords=keywords,
            robots=robots,
            canonical_url=canonical_url,
            og_title=og_title,
            og_description=og_description,
            og_image=og_image,
            og_url=og_url,
            og_site_name=og_site_name,
        )

    async def _wait_for_spa_stability(
        self,
        page: Page,
        timeout_ms: int = 5000,
    ) -> None:
        """Wait for SPA content to stop changing.

        Checks DOM content hash every 200ms, considers stable after
        3 consecutive identical hashes.

        Args:
            page: Playwright page instance
            timeout_ms: Maximum wait time in milliseconds
        """
        start_time = asyncio.get_event_loop().time()
        max_wait = timeout_ms / 1000

        # Wait for at least one heading to appear
        try:
            await page.wait_for_selector("h1, h2, main, article", timeout=timeout_ms)
        except Exception:
            # If no heading found, continue anyway
            pass

        # Wait for content stability (DOM not changing)
        last_content_hash = ""
        stable_count = 0
        required_stable = 3  # Need 3 consecutive stable checks (600ms total)

        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                # Get current page content hash
                content = await page.content()
                current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

                if current_hash == last_content_hash:
                    stable_count += 1
                    if stable_count >= required_stable:
                        LOGGER.debug(f"SPA content stable after {stable_count} checks")
                        return
                else:
                    stable_count = 0
                    last_content_hash = current_hash

                await asyncio.sleep(0.2)  # Check every 200ms
            except Exception as e:
                LOGGER.warning(f"Error checking content stability: {e}")
                break

        LOGGER.debug("SPA content wait timed out, proceeding anyway")
