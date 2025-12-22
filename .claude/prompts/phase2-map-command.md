# Phase 2: Map Command Implementation

## Context

You are implementing Phase 2 of the Firecrawl-parity rebuild for the web-scraper project. This phase creates the `map` command that discovers all URLs on a website.

**Branch:** `refactor/firecrawl-parity-v2`
**Issues:** #4-14 (see below for breakdown)
**Depends On:** Phase 1 (BrowserManager, MarkdownConverter) - COMPLETED

## Prerequisites

Before starting, ensure Phase 1 components are available:
```bash
python -c "from web_scraper.browser import BrowserManager; print('OK')"
```

## Phase 2 Goals

Build a standalone `map` command that:
1. Discovers all URLs on a website via BFS crawling
2. Integrates sitemap.xml for comprehensive discovery
3. Extracts title and description for each URL
4. Outputs Firecrawl-compatible JSON format
5. Uses our BrowserManager (NOT Crawl4AI)

## Task Breakdown by Issue

### Issue #4: Standalone map function
Create `web_scraper/services/map.py` with the core MapService class.

### Issue #5: Multi-hop discovery
Implement BFS with configurable depth limit.

### Issue #6: Sitemap integration
Support `--sitemap include|skip|only` modes.

### Issue #7: Domain boundary enforcement
Stay within the starting domain (with optional subdomain support).

### Issue #8: Link deduplication
Track visited URLs to avoid duplicates.

### Issue #9: Limit parameter
Support `--limit N` to cap discovered URLs.

### Issue #10: Search filter
Support `--search TEXT` to filter URLs containing text.

### Issue #11: Title extraction
Extract page titles for each discovered URL.

### Issue #12: Description extraction
Extract meta descriptions for each URL.

### Issue #14: JSON output format
Match Firecrawl's output structure exactly.

---

## Implementation Guide

### Directory Structure

Create these files:
```
web_scraper/
├── services/
│   ├── __init__.py
│   └── map.py          # MapService class
├── models/
│   ├── __init__.py
│   └── map.py          # MapLink, MapResult models
```

### Data Models (`web_scraper/models/map.py`)

```python
"""Map command data models."""

from __future__ import annotations

from pydantic import BaseModel, HttpUrl


class MapLink(BaseModel):
    """A discovered URL with metadata."""
    url: str
    title: str | None = None
    description: str | None = None


class MapResult(BaseModel):
    """Result of a map operation."""
    success: bool
    links: list[MapLink]
    error: str | None = None
```

### MapService Interface (`web_scraper/services/map.py`)

```python
"""Map service for URL discovery."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from web_scraper.browser import BrowserManager
from web_scraper.models.map import MapLink, MapResult

LOGGER = logging.getLogger(__name__)


class MapService:
    """Discover all URLs on a website.

    Usage:
        service = MapService()
        result = await service.map("https://example.com")
        for link in result.links:
            print(link.url, link.title)
    """

    def __init__(self, browser: BrowserManager | None = None):
        """Initialize map service.

        Args:
            browser: Optional BrowserManager (created if not provided)
        """
        self._browser = browser
        self._owns_browser = browser is None

    async def map(
        self,
        url: str,
        limit: int = 200,
        max_depth: int = 3,
        sitemap: Literal["include", "skip", "only"] = "include",
        include_subdomains: bool = False,
        search: str | None = None,
    ) -> MapResult:
        """Map a website and discover URLs.

        Args:
            url: Starting URL
            limit: Maximum URLs to return
            max_depth: Maximum BFS depth
            sitemap: Sitemap handling mode
            include_subdomains: Include subdomain URLs
            search: Filter URLs containing this text

        Returns:
            MapResult with discovered links
        """
        # TODO: Implement
        # 1. Parse starting URL for domain
        # 2. If sitemap != "skip", fetch sitemap URLs
        # 3. If sitemap != "only", BFS crawl from starting URL
        # 4. For each URL, extract title and description
        # 5. Apply search filter if provided
        # 6. Return MapResult
        pass

    async def _fetch_sitemap(self, base_url: str) -> list[str]:
        """Fetch and parse sitemap.xml.

        Args:
            base_url: Base URL of the site

        Returns:
            List of URLs from sitemap
        """
        # TODO: Implement
        # 1. Try /sitemap.xml
        # 2. Try /sitemap_index.xml
        # 3. Parse XML and extract loc elements
        # 4. Handle nested sitemaps
        pass

    async def _bfs_crawl(
        self,
        start_url: str,
        domain: str,
        max_depth: int,
        limit: int,
        include_subdomains: bool,
    ) -> list[str]:
        """BFS crawl to discover URLs.

        Args:
            start_url: Starting URL
            domain: Base domain to stay within
            max_depth: Maximum depth
            limit: Maximum URLs to discover
            include_subdomains: Include subdomains

        Returns:
            List of discovered URLs
        """
        # TODO: Implement
        # 1. Initialize queue with (start_url, depth=0)
        # 2. Track visited URLs
        # 3. For each URL, extract links
        # 4. Filter links to stay within domain
        # 5. Add new links to queue if depth < max_depth
        # 6. Stop when limit reached or queue empty
        pass

    async def _extract_metadata(self, url: str) -> tuple[str | None, str | None]:
        """Extract title and description from a URL.

        Args:
            url: URL to extract metadata from

        Returns:
            Tuple of (title, description)
        """
        # TODO: Implement using BrowserManager
        pass

    def _is_same_domain(
        self,
        url: str,
        base_domain: str,
        include_subdomains: bool,
    ) -> bool:
        """Check if URL is within the allowed domain.

        Args:
            url: URL to check
            base_domain: Base domain
            include_subdomains: Include subdomains

        Returns:
            True if URL is within domain
        """
        # TODO: Implement
        pass
```

### CLI Integration (`web_scraper/cli.py`)

Add a new `map` command:

```python
@cli.command()
@click.argument("url")
@click.option("--limit", default=200, help="Maximum URLs to discover")
@click.option("--depth", default=3, help="Maximum crawl depth")
@click.option("--sitemap", type=click.Choice(["include", "skip", "only"]), default="include")
@click.option("--include-subdomains", is_flag=True, help="Include subdomain URLs")
@click.option("--search", help="Filter URLs containing this text")
@click.option("--output", "-o", type=click.Path(), help="Output file (JSON)")
def map(url: str, limit: int, depth: int, sitemap: str, include_subdomains: bool, search: str | None, output: str | None):
    """Map a website to discover all URLs.

    Examples:
        web-scraper map https://example.com
        web-scraper map https://example.com --limit 50 --output urls.json
    """
    import asyncio
    from web_scraper.services.map import MapService

    async def run():
        service = MapService()
        result = await service.map(
            url=url,
            limit=limit,
            max_depth=depth,
            sitemap=sitemap,
            include_subdomains=include_subdomains,
            search=search,
        )
        return result

    result = asyncio.run(run())

    # Output handling
    if output:
        import json
        with open(output, "w") as f:
            json.dump(result.model_dump(), f, indent=2)
        click.echo(f"Wrote {len(result.links)} URLs to {output}")
    else:
        # Print to stdout
        for link in result.links:
            click.echo(link.url)
```

---

## Key Implementation Notes

### 1. BFS Crawling Algorithm

```python
async def _bfs_crawl(self, start_url, domain, max_depth, limit, include_subdomains):
    visited = set()
    queue = deque([(start_url, 0)])  # (url, depth)
    discovered = []

    while queue and len(discovered) < limit:
        url, depth = queue.popleft()

        if url in visited:
            continue
        visited.add(url)

        if not self._is_same_domain(url, domain, include_subdomains):
            continue

        discovered.append(url)

        if depth < max_depth:
            # Extract links from this page
            links = await self._extract_links(url)
            for link in links:
                if link not in visited:
                    queue.append((link, depth + 1))

    return discovered
```

### 2. Sitemap Parsing

Use httpx for fast sitemap fetching (no browser needed):

```python
async def _fetch_sitemap(self, base_url):
    urls = []
    sitemap_urls = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
    ]

    async with httpx.AsyncClient() as client:
        for sitemap_url in sitemap_urls:
            try:
                resp = await client.get(sitemap_url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "xml")
                    # Handle sitemap index
                    for sitemap in soup.find_all("sitemap"):
                        loc = sitemap.find("loc")
                        if loc:
                            # Recursively fetch nested sitemap
                            nested = await self._fetch_sitemap_url(client, loc.text)
                            urls.extend(nested)
                    # Handle regular sitemap
                    for url in soup.find_all("loc"):
                        urls.append(url.text)
            except Exception as e:
                LOGGER.debug(f"Sitemap fetch failed: {e}")

    return list(set(urls))  # Deduplicate
```

### 3. Domain Checking

```python
def _is_same_domain(self, url, base_domain, include_subdomains):
    parsed = urlparse(url)
    url_domain = parsed.netloc.lower()
    base = base_domain.lower()

    if include_subdomains:
        return url_domain == base or url_domain.endswith(f".{base}")
    else:
        return url_domain == base
```

### 4. Firecrawl-Compatible Output

Firecrawl returns:
```json
{
  "success": true,
  "links": [
    {"url": "https://example.com/page1", "title": "Page 1", "description": "..."},
    {"url": "https://example.com/page2", "title": "Page 2", "description": "..."}
  ]
}
```

---

## Unit Tests (`tests/unit/test_map_service.py`)

```python
"""Tests for map service."""

import pytest
from web_scraper.services.map import MapService
from web_scraper.models.map import MapLink, MapResult


class TestMapService:
    """Tests for MapService."""

    @pytest.mark.asyncio
    async def test_map_returns_links(self):
        """Test that map returns discovered links."""
        service = MapService()
        result = await service.map("https://example.com", limit=10)
        assert isinstance(result, MapResult)
        assert result.success
        assert len(result.links) > 0

    @pytest.mark.asyncio
    async def test_map_respects_limit(self):
        """Test that map respects URL limit."""
        service = MapService()
        result = await service.map("https://example.com", limit=5)
        assert len(result.links) <= 5

    @pytest.mark.asyncio
    async def test_map_extracts_titles(self):
        """Test that map extracts page titles."""
        service = MapService()
        result = await service.map("https://example.com", limit=5)
        # At least one link should have a title
        titles = [link.title for link in result.links if link.title]
        assert len(titles) > 0

    def test_is_same_domain_exact(self):
        """Test domain matching without subdomains."""
        service = MapService()
        assert service._is_same_domain("https://example.com/page", "example.com", False)
        assert not service._is_same_domain("https://sub.example.com/page", "example.com", False)

    def test_is_same_domain_with_subdomains(self):
        """Test domain matching with subdomains."""
        service = MapService()
        assert service._is_same_domain("https://sub.example.com/page", "example.com", True)
        assert service._is_same_domain("https://example.com/page", "example.com", True)
        assert not service._is_same_domain("https://other.com/page", "example.com", True)

    @pytest.mark.asyncio
    async def test_search_filter(self):
        """Test URL filtering with search."""
        service = MapService()
        result = await service.map("https://example.com", limit=100, search="about")
        # All URLs should contain "about"
        for link in result.links:
            assert "about" in link.url.lower() or len(result.links) == 0
```

---

## Verification Checklist

After implementation, verify:

- [ ] `python -c "from web_scraper.services.map import MapService"` works
- [ ] `pytest tests/unit/test_map_service.py -v` passes
- [ ] No `crawl4ai` imports in new files
- [ ] No `CRAWL4AI_*` env vars in new files
- [ ] CLI command works: `web-scraper map https://example.com --limit 10`

### Firecrawl Parity Test

Compare against Firecrawl baseline:

```bash
# Our tool
web-scraper map https://portfolio.sharesight.com/api --limit 20 --output /tmp/our-map.json

# Should find 14+ URLs including /api/2/* and /api/3/*
python -c "import json; d=json.load(open('/tmp/our-map.json')); print(f'Found {len(d[\"links\"])} URLs')"

# List the URLs
python -c "import json; d=json.load(open('/tmp/our-map.json')); print('\n'.join(l['url'] for l in d['links']))"
```

---

## Commit Message

When complete, commit with:

```
feat: add map command for URL discovery

- Add MapService for website URL discovery (#4)
- Implement multi-hop BFS discovery (#5)
- Add sitemap.xml integration (#6)
- Enforce domain boundaries (#7)
- Add link deduplication (#8)
- Support --limit parameter (#9)
- Support --search filter (#10)
- Extract page titles (#11)
- Extract meta descriptions (#12)
- Output Firecrawl-compatible JSON (#14)
- Add unit tests

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Next Steps

After Phase 2 is complete, proceed to Phase 3 (Scrape command) using issues #17-18.
