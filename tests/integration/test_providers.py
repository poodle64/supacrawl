"""Provider integration tests for Crawl4AI wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from web_scraper.exceptions import ProviderError
from web_scraper.models import SiteConfig
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper


def _site_config(*_: Any, **__: Any) -> SiteConfig:
    """Return a minimal site config for tests."""
    return SiteConfig(
        id="example",
        name="Example",
        entrypoints=["https://example.com"],
        include=["https://example.com"],
        exclude=[],
        max_pages=5,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
    )


def _make_crawl_result(
    url: str,
    title: str,
    content: str,
    success: bool = True,
) -> MagicMock:
    """Create a mock CrawlResult with proper markdown structure."""
    mock_result = MagicMock()
    mock_result.success = success
    mock_result.url = url
    mock_result.title = title
    # Add more realistic HTML with multiple paragraphs to pass language detection
    mock_result.html = f"""<html><body>
        <h1>{title}</h1>
        <p>{content}</p>
        <p>This is additional English content for the page.</p>
        <p>More content here to ensure language detection works properly.</p>
    </body></html>"""
    mock_result.cleaned_html = mock_result.html

    # Markdown attribute must be an object with raw_markdown and fit_markdown
    mock_markdown = MagicMock()
    # Create markdown content that passes language detection filters
    markdown_content = f"""# {title}

{content}

This is additional English content for the page.

More content here to ensure language detection works properly."""
    mock_markdown.raw_markdown = markdown_content
    mock_markdown.fit_markdown = markdown_content
    mock_result.markdown = mock_markdown

    mock_result.metadata = {}
    mock_result.links = {}
    mock_result.status_code = 200
    return mock_result


def test_crawl4ai_happy_path(tmp_path: Path) -> None:
    """Crawl4AI scraper should parse SDK response into Page models."""
    # Create mock CrawlResult objects
    mock_result_1 = _make_crawl_result(
        url="https://example.com/page",
        title="Page Title",
        content="Example content",
    )
    mock_result_2 = _make_crawl_result(
        url="https://example.com/page2",
        title="Page 2",
        content="More content",
    )

    # Create mock AsyncWebCrawler
    mock_crawler = AsyncMock()
    mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = AsyncMock(return_value=None)
    mock_crawler.arun = AsyncMock(return_value=[mock_result_1, mock_result_2])

    scraper = Crawl4AIScraper(crawler=mock_crawler)
    pages, snapshot_path = scraper.crawl(_site_config(), corpora_dir=tmp_path)

    assert len(pages) == 2
    assert pages[0].url == "https://example.com/page"
    # The content may be processed/filtered, but should contain meaningful content
    assert pages[0].content_markdown.strip(), "Content should not be empty"
    assert pages[1].url == "https://example.com/page2"
    assert snapshot_path.exists()


def test_crawl4ai_playwright_browser_missing(tmp_path: Path) -> None:
    """Crawl4AI should provide helpful error when Playwright browsers are missing."""
    # Create mock crawler that raises Playwright browser error
    mock_crawler = AsyncMock()

    # Create a custom exception that mimics Playwright's error
    class PlaywrightError(Exception):
        pass

    playwright_error = PlaywrightError(
        "BrowserType.launch: Executable doesn't exist at /path/to/chrome"
    )
    mock_crawler.__aenter__ = AsyncMock(side_effect=playwright_error)

    scraper = Crawl4AIScraper(crawler=mock_crawler)

    with pytest.raises(ProviderError) as exc_info:
        scraper.crawl(_site_config("crawl4ai"), corpora_dir=tmp_path)

    error_message = str(exc_info.value)
    assert (
        "Playwright browsers" in error_message
        or "playwright install" in error_message.lower()
        or "failed to initialise" in error_message.lower()
    )


def test_crawl4ai_raises_provider_error_on_sdk_failure(tmp_path: Path) -> None:
    """Crawl4AI scraper should wrap SDK errors with ProviderError."""
    # Create mock crawler that raises an error
    mock_crawler = AsyncMock()
    mock_crawler.__aenter__ = AsyncMock(side_effect=RuntimeError("SDK error"))

    scraper = Crawl4AIScraper(crawler=mock_crawler)

    with pytest.raises(ProviderError) as exc_info:
        scraper.crawl(_site_config("crawl4ai"), corpora_dir=tmp_path)

    assert "Crawl4AI" in str(exc_info.value)
    assert "correlation_id=" in str(exc_info.value)


def test_crawl4ai_multiple_entrypoints(tmp_path: Path) -> None:
    """Crawl4AI scraper should handle multiple entrypoints."""
    # Create mock results for each entrypoint
    mock_result_1 = _make_crawl_result(
        url="https://example.com/page1",
        title="Page 1",
        content="Content from page1",
    )
    mock_result_2 = _make_crawl_result(
        url="https://example.com/page2",
        title="Page 2",
        content="Content from page2",
    )

    # Create mock crawler that returns different results per entrypoint
    mock_crawler = AsyncMock()
    mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = AsyncMock(return_value=None)

    # First call returns result 1, second call returns result 2
    mock_crawler.arun = AsyncMock(
        side_effect=[
            [mock_result_1],
            [mock_result_2],
        ]
    )

    config = SiteConfig(
        id="multi",
        name="Multi",
        entrypoints=["https://example.com/page1", "https://example.com/page2"],
        include=["https://example.com/**"],
        exclude=[],
        max_pages=10,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
    )

    scraper = Crawl4AIScraper(crawler=mock_crawler)
    pages, _ = scraper.crawl(config, corpora_dir=tmp_path)

    assert mock_crawler.arun.call_count == 2
    assert len(pages) == 2
    assert pages[0].url == "https://example.com/page1"
    assert pages[1].url == "https://example.com/page2"
