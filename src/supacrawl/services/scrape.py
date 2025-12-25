"""Scrape service for single URL content extraction (Firecrawl-compatible)."""

from __future__ import annotations

import base64
import logging
from typing import Literal

from bs4 import BeautifulSoup

from supacrawl.services.browser import BrowserManager
from supacrawl.services.converter import MarkdownConverter
from supacrawl.models import ScrapeData, ScrapeMetadata, ScrapeResult

LOGGER = logging.getLogger(__name__)


class ScrapeService:
    """Scrape a single URL and extract content (Firecrawl-compatible).

    Usage:
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        print(result.data.markdown)
    """

    def __init__(
        self,
        browser: BrowserManager | None = None,
        converter: MarkdownConverter | None = None,
    ):
        """Initialize scrape service.

        Args:
            browser: Optional BrowserManager (created if not provided)
            converter: Optional MarkdownConverter (created if not provided)
        """
        self._browser = browser
        self._converter = converter or MarkdownConverter()
        self._owns_browser = browser is None

    async def scrape(
        self,
        url: str,
        formats: list[Literal["markdown", "html", "rawHtml", "links", "screenshot", "pdf"]] | None = None,
        only_main_content: bool = True,
        wait_for: int = 0,
        timeout: int = 30000,
        screenshot_full_page: bool = True,
    ) -> ScrapeResult:
        """Scrape a URL and return content.

        Args:
            url: URL to scrape
            formats: Content formats to return (default: ["markdown"])
                     Supports: markdown, html, rawHtml, links, screenshot, pdf
            only_main_content: Extract main content area only
            wait_for: Additional wait time in ms after page load
            timeout: Page load timeout in ms
            screenshot_full_page: Capture full scrollable page for screenshots

        Returns:
            ScrapeResult with scraped content
        """
        formats = formats or ["markdown"]

        try:
            # Create browser if needed
            browser = self._browser
            owns_browser = self._owns_browser

            if owns_browser:
                browser = BrowserManager(timeout_ms=timeout)
                await browser.__aenter__()

            try:
                # Determine if we need screenshot or PDF capture
                capture_screenshot = "screenshot" in formats
                capture_pdf = "pdf" in formats

                # Fetch page
                page_content = await browser.fetch_page(
                    url,
                    wait_for_spa=True,
                    spa_timeout_ms=wait_for if wait_for > 0 else 5000,
                    capture_screenshot=capture_screenshot,
                    capture_pdf=capture_pdf,
                    screenshot_full_page=screenshot_full_page,
                )

                # Extract metadata
                metadata = await browser.extract_metadata(page_content.html)

                # Build response based on requested formats
                markdown = None
                html = None
                raw_html = None
                links = None
                screenshot_b64 = None
                pdf_b64 = None

                if "markdown" in formats:
                    markdown = self._converter.convert(
                        page_content.html,
                        base_url=url,
                        only_main_content=only_main_content,
                    )

                if "html" in formats:
                    # Clean HTML (boilerplate removed)
                    html = self._get_clean_html(page_content.html, only_main_content)

                if "rawHtml" in formats:
                    raw_html = page_content.html

                if "links" in formats:
                    links = await browser.extract_links(url)

                if capture_screenshot and page_content.screenshot:
                    screenshot_b64 = base64.b64encode(page_content.screenshot).decode("utf-8")

                if capture_pdf and page_content.pdf:
                    pdf_b64 = base64.b64encode(page_content.pdf).decode("utf-8")

                # Compute word count from markdown
                word_count = len(markdown.split()) if markdown else None

                return ScrapeResult(
                    success=True,
                    data=ScrapeData(
                        markdown=markdown,
                        html=html,
                        raw_html=raw_html,
                        screenshot=screenshot_b64,
                        pdf=pdf_b64,
                        metadata=ScrapeMetadata(
                            # Core metadata
                            title=metadata.title,
                            description=metadata.description,
                            language=metadata.language,
                            keywords=metadata.keywords,
                            robots=metadata.robots,
                            canonical_url=metadata.canonical_url,
                            # OpenGraph metadata
                            og_title=metadata.og_title,
                            og_description=metadata.og_description,
                            og_image=metadata.og_image,
                            og_url=metadata.og_url,
                            og_site_name=metadata.og_site_name,
                            # Source information
                            source_url=url,
                            status_code=page_content.status_code,
                            # Content metrics
                            word_count=word_count,
                        ),
                        links=links,
                    ),
                )

            finally:
                if owns_browser and browser:
                    await browser.__aexit__(None, None, None)

        except Exception as e:
            LOGGER.error(f"Scrape failed for {url}: {e}", exc_info=True)
            return ScrapeResult(
                success=False,
                error=str(e),
            )

    def _get_clean_html(self, html: str, only_main_content: bool) -> str:
        """Get cleaned HTML with boilerplate removed.

        Args:
            html: Raw HTML
            only_main_content: Extract main content only

        Returns:
            Cleaned HTML string
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove boilerplate
        for tag_name in ["script", "style", "nav", "footer", "header", "noscript", "iframe"]:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Find main content if requested
        if only_main_content:
            for selector in ["main", "article", "[role='main']", ".content", "#content"]:
                main = soup.select_one(selector)
                if main:
                    return str(main)

        body = soup.find("body")
        return str(body) if body else str(soup)
