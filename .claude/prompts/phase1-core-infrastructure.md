# Phase 1: Core Infrastructure Implementation

## Context

You are implementing Phase 1 of the Firecrawl-parity rebuild for the web-scraper project. This phase creates the core components that replace Crawl4AI with our own Playwright-based stack.

**Branch:** `refactor/firecrawl-parity-v2`
**Issues:** #15 (Browser Manager), #16 (Markdown Converter)

## Prerequisites

Before starting, ensure you're on the correct branch:
```bash
git checkout refactor/firecrawl-parity-v2
```

## Task 1: Browser Manager (#15)

Create `web_scraper/browser.py` - a Playwright-based browser manager.

### Requirements

1. **BrowserManager class** with async context manager support
2. **Fresh context per URL** (critical for SPA handling)
3. **SPA content stability detection** (wait for DOM to stop changing)
4. **Configurable via WEB_SCRAPER_* env vars** (not CRAWL4AI_*)

### Interface to Implement

```python
"""Browser manager for Playwright-based page fetching."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

LOGGER = logging.getLogger(__name__)


@dataclass
class PageContent:
    """Result of fetching a page."""
    url: str
    html: str
    title: str | None
    status_code: int


@dataclass
class PageMetadata:
    """Metadata extracted from a page."""
    title: str | None
    description: str | None
    og_title: str | None
    og_description: str | None
    og_image: str | None


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
            headless: Run headless (default from WEB_SCRAPER_HEADLESS env, or True)
            timeout_ms: Page load timeout (default from WEB_SCRAPER_TIMEOUT env, or 30000)
            user_agent: User agent string (default from WEB_SCRAPER_USER_AGENT env)
        """
        self.headless = headless if headless is not None else self._env_bool("WEB_SCRAPER_HEADLESS", True)
        self.timeout_ms = timeout_ms or int(os.getenv("WEB_SCRAPER_TIMEOUT", "30000"))
        self.user_agent = user_agent or os.getenv(
            "WEB_SCRAPER_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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
        """Start browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def fetch_page(
        self,
        url: str,
        wait_for_spa: bool = True,
        spa_timeout_ms: int = 5000,
    ) -> PageContent:
        """Fetch a page with browser rendering.

        Args:
            url: URL to fetch
            wait_for_spa: Wait for SPA content to stabilize
            spa_timeout_ms: Max time to wait for SPA stability

        Returns:
            PageContent with HTML and metadata
        """
        # TODO: Implement
        # 1. Create fresh context
        # 2. Navigate to URL
        # 3. Wait for SPA stability if requested
        # 4. Extract HTML and title
        # 5. Close context
        pass

    async def extract_links(self, url: str) -> list[str]:
        """Extract all links from a rendered page.

        Args:
            url: URL to fetch and extract links from

        Returns:
            List of absolute URLs found on the page
        """
        # TODO: Implement
        pass

    async def extract_metadata(self, html: str) -> PageMetadata:
        """Extract metadata from HTML.

        Args:
            html: HTML content

        Returns:
            PageMetadata with title, description, og tags
        """
        # TODO: Implement using BeautifulSoup
        pass

    async def _wait_for_spa_stability(
        self,
        page: Page,
        timeout_ms: int = 5000,
    ) -> None:
        """Wait for SPA content to stop changing.

        Checks DOM content hash every 200ms, considers stable after
        3 consecutive identical hashes.
        """
        # TODO: Implement
        # Copy logic from playwright_scraper.py _wait_for_spa_content
        pass
```

### Implementation Notes

1. Copy SPA stability logic from `web_scraper/scrapers/playwright_scraper.py` `_wait_for_spa_content()`
2. Use BeautifulSoup for metadata extraction
3. Always create fresh context per fetch (not reuse)
4. Log with correlation IDs where appropriate

### Environment Variables

Replace all CRAWL4AI_* with WEB_SCRAPER_*:
- `WEB_SCRAPER_HEADLESS` (default: true)
- `WEB_SCRAPER_TIMEOUT` (default: 30000)
- `WEB_SCRAPER_SPA_DELAY` (default: 2.0)
- `WEB_SCRAPER_USER_AGENT`
- `WEB_SCRAPER_LOCALE` (default: en-US)
- `WEB_SCRAPER_TIMEZONE` (default: Australia/Brisbane)

---

## Task 2: Markdown Converter (#16)

Create `web_scraper/converter.py` - HTML to Markdown converter with Firecrawl parity.

### Requirements

1. **MarkdownConverter class** with clean interface
2. **Firecrawl-compatible output** (ATX headings, dash bullets, etc.)
3. **Boilerplate removal** (nav, footer, header, ads)
4. **Main content extraction** (find article/main element)

### Interface to Implement

```python
"""HTML to Markdown converter with Firecrawl output parity."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

LOGGER = logging.getLogger(__name__)


class MarkdownConverter:
    """Convert HTML to Firecrawl-compatible markdown.

    Usage:
        converter = MarkdownConverter()
        markdown = converter.convert(html)
    """

    # Tags to remove completely
    REMOVE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "iframe", "svg"]

    # Selectors to try for main content (in order)
    MAIN_CONTENT_SELECTORS = [
        "main",
        "article",
        "[role='main']",
        ".content",
        "#content",
        ".main-content",
        ".post-content",
        ".article-content",
    ]

    def convert(
        self,
        html: str,
        only_main_content: bool = True,
        remove_boilerplate: bool = True,
    ) -> str:
        """Convert HTML to markdown.

        Args:
            html: Raw HTML content
            only_main_content: Extract main content area only
            remove_boilerplate: Remove nav, footer, ads, etc.

        Returns:
            Clean markdown string
        """
        # TODO: Implement
        # 1. Parse HTML with BeautifulSoup
        # 2. Remove boilerplate tags if requested
        # 3. Find main content if requested
        # 4. Convert to markdown with markdownify
        # 5. Clean up whitespace
        pass

    def _remove_boilerplate(self, soup: BeautifulSoup) -> None:
        """Remove boilerplate elements in-place."""
        # TODO: Implement
        pass

    def _find_main_content(self, soup: BeautifulSoup) -> Tag | None:
        """Find the main content element."""
        # TODO: Implement
        pass

    def _clean_whitespace(self, markdown: str) -> str:
        """Clean up excessive whitespace."""
        # TODO: Implement
        # - Collapse multiple blank lines to max 2
        # - Strip trailing whitespace per line
        # - Strip leading/trailing whitespace from document
        pass
```

### Markdownify Options for Firecrawl Parity

```python
markdown = md(
    html,
    heading_style="atx",      # Use # style headings
    bullets="-",              # Use - for unordered lists
    code_language="",         # Don't assume language for code blocks
    strip=["script", "style", "nav", "footer", "header"],
    wrap=False,               # Don't wrap lines
    wrap_width=0,             # No line width limit
)
```

### Implementation Notes

1. Copy relevant logic from `playwright_scraper.py` `_html_to_markdown()`
2. Test against Firecrawl output for same URLs
3. Handle edge cases: empty content, malformed HTML

---

## Task 3: Unit Tests

Create tests for both components.

### Browser Manager Tests (`tests/unit/test_browser.py`)

```python
"""Tests for browser manager."""

import pytest
from web_scraper.browser import BrowserManager, PageContent, PageMetadata


class TestBrowserManager:
    """Tests for BrowserManager."""

    @pytest.mark.asyncio
    async def test_fetch_page_returns_html(self):
        """Test that fetch_page returns HTML content."""
        async with BrowserManager() as browser:
            content = await browser.fetch_page("https://example.com")
            assert content.html
            assert "<html" in content.html.lower()

    @pytest.mark.asyncio
    async def test_extract_links_finds_links(self):
        """Test that extract_links finds anchor tags."""
        async with BrowserManager() as browser:
            links = await browser.extract_links("https://example.com")
            assert isinstance(links, list)

    def test_extract_metadata_from_html(self):
        """Test metadata extraction from HTML."""
        # TODO: Add test with sample HTML
        pass
```

### Markdown Converter Tests (`tests/unit/test_converter.py`)

```python
"""Tests for markdown converter."""

import pytest
from web_scraper.converter import MarkdownConverter


class TestMarkdownConverter:
    """Tests for MarkdownConverter."""

    def test_converts_headings_to_atx(self):
        """Test that headings use ATX style (#)."""
        converter = MarkdownConverter()
        html = "<h1>Title</h1><h2>Subtitle</h2>"
        md = converter.convert(html, only_main_content=False)
        assert "# Title" in md
        assert "## Subtitle" in md

    def test_removes_script_tags(self):
        """Test that script tags are removed."""
        converter = MarkdownConverter()
        html = "<p>Content</p><script>alert('x')</script>"
        md = converter.convert(html, only_main_content=False)
        assert "alert" not in md
        assert "Content" in md

    def test_preserves_links(self):
        """Test that links are preserved."""
        converter = MarkdownConverter()
        html = '<a href="https://example.com">Link</a>'
        md = converter.convert(html, only_main_content=False)
        assert "[Link](https://example.com)" in md

    def test_preserves_code_blocks(self):
        """Test that code blocks are preserved."""
        converter = MarkdownConverter()
        html = "<pre><code>def foo(): pass</code></pre>"
        md = converter.convert(html, only_main_content=False)
        assert "def foo(): pass" in md

    def test_cleans_whitespace(self):
        """Test that excessive whitespace is cleaned."""
        converter = MarkdownConverter()
        html = "<p>A</p><p></p><p></p><p></p><p>B</p>"
        md = converter.convert(html, only_main_content=False)
        # Should not have more than 2 consecutive blank lines
        assert "\n\n\n\n" not in md
```

---

## Verification Checklist

After implementation, verify:

- [ ] `python -c "from web_scraper.browser import BrowserManager"` works
- [ ] `python -c "from web_scraper.converter import MarkdownConverter"` works
- [ ] `pytest tests/unit/test_browser.py -v` passes
- [ ] `pytest tests/unit/test_converter.py -v` passes
- [ ] No `crawl4ai` imports in new files
- [ ] No `CRAWL4AI_*` env vars in new files

## Commit Message

When complete, commit with:

```
feat: add core infrastructure for Firecrawl parity

- Add BrowserManager for Playwright-based page fetching (#15)
- Add MarkdownConverter for HTML to markdown with Firecrawl parity (#16)
- Add unit tests for both components
- Use WEB_SCRAPER_* env vars instead of CRAWL4AI_*

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Next Steps

After Phase 1 is complete, proceed to Phase 2 (Map) using the issues #4-14.
