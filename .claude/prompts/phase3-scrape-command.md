# Phase 3: Scrape Command Implementation

## Context

You are implementing Phase 3 of the Firecrawl-parity rebuild for the web-scraper project. This phase creates the `scrape` command for single URL scraping.

**Branch:** `refactor/firecrawl-parity-v2`
**Issues:** #17, #18
**Depends On:** Phase 1 (BrowserManager, MarkdownConverter) - COMPLETED

## Prerequisites

Before starting, ensure Phase 1 components are available:
```bash
python -c "from web_scraper.browser import BrowserManager; from web_scraper.converter import MarkdownConverter; print('OK')"
```

## Phase 3 Goals

Build a standalone `scrape` command that:
1. Fetches a single URL with browser rendering
2. Converts HTML to clean markdown
3. Extracts metadata (title, description, og tags)
4. Outputs Firecrawl-compatible JSON format
5. Uses our BrowserManager and MarkdownConverter (NOT Crawl4AI)

## Task Breakdown by Issue

### Issue #17: Standalone scrape function
Create `web_scraper/services/scrape.py` with the core ScrapeService class.

### Issue #18: Firecrawl output format
Return markdown, html, and metadata in Firecrawl's format.

---

## Implementation Guide

### Data Models (`web_scraper/models/scrape.py`)

```python
"""Scrape command data models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ScrapeMetadata(BaseModel):
    """Metadata extracted from a page."""
    title: str | None = None
    description: str | None = None
    language: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    og_image: str | None = None
    source_url: str | None = None
    status_code: int | None = None


class ScrapeData(BaseModel):
    """Scraped content from a page."""
    markdown: str | None = None
    html: str | None = None
    raw_html: str | None = None
    metadata: ScrapeMetadata
    links: list[str] | None = None


class ScrapeResult(BaseModel):
    """Result of a scrape operation."""
    success: bool
    data: ScrapeData | None = None
    error: str | None = None
```

### ScrapeService Interface (`web_scraper/services/scrape.py`)

```python
"""Scrape service for single URL content extraction."""

from __future__ import annotations

import logging
from typing import Literal

from web_scraper.browser import BrowserManager
from web_scraper.converter import MarkdownConverter
from web_scraper.models.scrape import ScrapeData, ScrapeMetadata, ScrapeResult

LOGGER = logging.getLogger(__name__)


class ScrapeService:
    """Scrape a single URL and extract content.

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
            LOGGER.error(f"Scrape failed for {url}: {e}")
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
        from bs4 import BeautifulSoup

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
```

### CLI Integration (`web_scraper/cli.py`)

Add a new `scrape` command:

```python
@cli.command()
@click.argument("url")
@click.option("--format", "-f", "formats", multiple=True,
              type=click.Choice(["markdown", "html", "rawHtml", "links"]),
              default=["markdown"], help="Output formats")
@click.option("--only-main-content/--no-only-main-content", default=True,
              help="Extract main content only")
@click.option("--wait-for", default=0, help="Additional wait time in ms")
@click.option("--timeout", default=30000, help="Page load timeout in ms")
@click.option("--output", "-o", type=click.Path(), help="Output file (JSON)")
def scrape(url: str, formats: tuple, only_main_content: bool, wait_for: int, timeout: int, output: str | None):
    """Scrape a single URL and extract content.

    Examples:
        web-scraper scrape https://example.com
        web-scraper scrape https://example.com --format markdown --format html
        web-scraper scrape https://example.com --output page.json
    """
    import asyncio
    from web_scraper.services.scrape import ScrapeService

    async def run():
        service = ScrapeService()
        result = await service.scrape(
            url=url,
            formats=list(formats),
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
        )
        return result

    result = asyncio.run(run())

    if output:
        import json
        with open(output, "w") as f:
            json.dump(result.model_dump(), f, indent=2)
        click.echo(f"Wrote scrape result to {output}")
    else:
        # Print markdown to stdout
        if result.success and result.data and result.data.markdown:
            click.echo(result.data.markdown)
        elif not result.success:
            click.echo(f"Error: {result.error}", err=True)
```

---

## Firecrawl Output Format Reference

Firecrawl returns:
```json
{
  "success": true,
  "data": {
    "markdown": "# Page Title\n\nContent...",
    "html": "<main>...</main>",
    "rawHtml": "<!DOCTYPE html>...",
    "metadata": {
      "title": "Page Title",
      "description": "Page description",
      "language": "en",
      "ogTitle": "OG Title",
      "ogDescription": "OG Description",
      "ogImage": "https://example.com/image.jpg",
      "sourceURL": "https://example.com/page",
      "statusCode": 200
    },
    "links": ["https://example.com/link1", "https://example.com/link2"]
  }
}
```

---

## Unit Tests (`tests/unit/test_scrape_service.py`)

```python
"""Tests for scrape service."""

import pytest
from web_scraper.services.scrape import ScrapeService
from web_scraper.models.scrape import ScrapeResult


class TestScrapeService:
    """Tests for ScrapeService."""

    @pytest.mark.asyncio
    async def test_scrape_returns_markdown(self):
        """Test that scrape returns markdown content."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert isinstance(result, ScrapeResult)
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert len(result.data.markdown) > 0

    @pytest.mark.asyncio
    async def test_scrape_extracts_metadata(self):
        """Test that scrape extracts page metadata."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert result.success
        assert result.data is not None
        assert result.data.metadata is not None
        assert result.data.metadata.title is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_html_when_requested(self):
        """Test that scrape returns HTML when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["html"])
        assert result.success
        assert result.data is not None
        assert result.data.html is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_links_when_requested(self):
        """Test that scrape returns links when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["links"])
        assert result.success
        assert result.data is not None
        assert result.data.links is not None
        assert isinstance(result.data.links, list)

    @pytest.mark.asyncio
    async def test_scrape_handles_error(self):
        """Test that scrape handles errors gracefully."""
        service = ScrapeService()
        result = await service.scrape("https://invalid-url-that-does-not-exist.example")
        assert not result.success
        assert result.error is not None
```

---

## Verification Checklist

After implementation, verify:

- [ ] `python -c "from web_scraper.services.scrape import ScrapeService"` works
- [ ] `pytest tests/unit/test_scrape_service.py -v` passes
- [ ] No `crawl4ai` imports in new files
- [ ] CLI command works: `web-scraper scrape https://example.com`
- [ ] JSON output matches Firecrawl format

---

## Commit Message

When complete, commit with:

```
feat: add scrape command for single URL extraction

- Add ScrapeService for single URL scraping (#17)
- Implement Firecrawl-compatible output format (#18)
- Support multiple output formats (markdown, html, rawHtml, links)
- Extract metadata (title, description, og tags)
- Add unit tests

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Next Steps

After Phase 3 is complete, proceed to Phase 4 (Crawl command) using issues #19-20.
