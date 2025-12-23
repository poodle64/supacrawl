"""Scrape service for single URL content extraction (Firecrawl-compatible)."""

from __future__ import annotations

import logging
from typing import Literal

from bs4 import BeautifulSoup

from web_scraper.browser import BrowserManager
from web_scraper.converter import MarkdownConverter
from web_scraper.models import ScrapeData, ScrapeMetadata, ScrapeResult

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
        formats: list[Literal["markdown", "html", "rawHtml", "links"]] | None = None,
        only_main_content: bool = True,
        wait_for: int = 0,
        timeout: int = 30000,
    ) -> ScrapeResult:
        """Scrape a URL and return content.

        Args:
            url: URL to scrape
            formats: Content formats to return (default: ["markdown"])
            only_main_content: Extract main content area only
            wait_for: Additional wait time in ms after page load
            timeout: Page load timeout in ms

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
                # Fetch page
                page_content = await browser.fetch_page(
                    url,
                    wait_for_spa=True,
                    spa_timeout_ms=wait_for if wait_for > 0 else 5000,
                )

                # Extract metadata
                metadata = await browser.extract_metadata(page_content.html)

                # Build response based on requested formats
                markdown = None
                html = None
                raw_html = None
                links = None

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

                return ScrapeResult(
                    success=True,
                    data=ScrapeData(
                        markdown=markdown,
                        html=html,
                        raw_html=raw_html,
                        metadata=ScrapeMetadata(
                            title=metadata.title,
                            description=metadata.description,
                            og_title=metadata.og_title,
                            og_description=metadata.og_description,
                            og_image=metadata.og_image,
                            source_url=url,
                            status_code=page_content.status_code,
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
