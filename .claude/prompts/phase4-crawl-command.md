# Phase 4: Crawl Command Implementation

## Context

You are implementing Phase 4 of the Firecrawl-parity rebuild for the web-scraper project. This phase creates the `crawl` command that combines map + scrape into a full-site crawling pipeline.

**Branch:** `refactor/firecrawl-parity-v2`
**Issues:** #19, #20
**Depends On:** Phase 2 (MapService), Phase 3 (ScrapeService)

## Prerequisites

Before starting, ensure Phase 2 and 3 components are available:
```bash
python -c "from web_scraper.map_service import MapService; from web_scraper.scrape_service import ScrapeService; print('OK')"
```

**IMPORTANT:** Sonnet placed services in `web_scraper/` root (not `web_scraper/services/`):
- `web_scraper/map_service.py` - MapService class
- `web_scraper/scrape_service.py` - ScrapeService class
- `web_scraper/models.py` - All Firecrawl-compatible models

Follow this pattern for consistency.

## Phase 4 Goals

Build a `crawl` command that:
1. Discovers URLs using MapService
2. Scrapes each URL using ScrapeService
3. Streams results as they complete (AsyncGenerator)
4. Supports progress reporting
5. Saves scraped content to output directory
6. Supports resume capability

## Task Breakdown by Issue

### Issue #19: CrawlService with map+scrape pipeline
Create `web_scraper/crawl_service.py` combining map and scrape.

### Issue #20: Progress reporting and resume
Add progress events and resume from previous crawl state.

---

## Implementation Guide

### Data Models (add to `web_scraper/models.py`)

```python
"""Crawl command data models."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel

from web_scraper.models import ScrapeData


class CrawlStatus(str, Enum):
    """Status of a crawl job."""
    SCRAPING = "scraping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrawlEvent(BaseModel):
    """Event emitted during crawl."""
    type: Literal["progress", "page", "complete", "error"]
    url: str | None = None
    data: ScrapeData | None = None
    completed: int = 0
    total: int = 0
    error: str | None = None


class CrawlResult(BaseModel):
    """Final result of a crawl job."""
    success: bool
    status: CrawlStatus
    completed: int
    total: int
    data: list[ScrapeData]
    errors: list[str] | None = None
```

### CrawlService Interface (`web_scraper/crawl_service.py`)

```python
"""Crawl service for full-site scraping."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator

from web_scraper.browser import BrowserManager
from web_scraper.converter import MarkdownConverter
from web_scraper.models import CrawlEvent, CrawlResult, CrawlStatus, ScrapeData
from web_scraper.map_service import MapService
from web_scraper.scrape_service import ScrapeService

LOGGER = logging.getLogger(__name__)


class CrawlService:
    """Crawl entire websites by combining map and scrape.

    Usage:
        service = CrawlService()
        async for event in service.crawl("https://example.com"):
            if event.type == "page":
                print(f"Scraped: {event.url}")
            elif event.type == "progress":
                print(f"Progress: {event.completed}/{event.total}")
    """

    def __init__(self):
        """Initialize crawl service."""
        self._browser: BrowserManager | None = None
        self._map_service: MapService | None = None
        self._scrape_service: ScrapeService | None = None

    async def crawl(
        self,
        url: str,
        limit: int = 100,
        max_depth: int = 3,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        output_dir: Path | None = None,
        resume: bool = False,
    ) -> AsyncGenerator[CrawlEvent, None]:
        """Crawl a website, yielding events as pages complete.

        Args:
            url: Starting URL
            limit: Maximum pages to crawl
            max_depth: Maximum crawl depth
            include_patterns: URL patterns to include
            exclude_patterns: URL patterns to exclude
            output_dir: Directory to save scraped content
            resume: Resume from previous crawl state

        Yields:
            CrawlEvent for each page and progress update
        """
        try:
            # Initialize browser and services
            async with BrowserManager() as browser:
                self._browser = browser
                self._map_service = MapService(browser=browser)
                self._scrape_service = ScrapeService(browser=browser)

                # Load resume state if requested
                scraped_urls = set()
                if resume and output_dir:
                    scraped_urls = self._load_resume_state(output_dir)
                    LOGGER.info(f"Resuming crawl with {len(scraped_urls)} already scraped")

                # Discover URLs
                LOGGER.info(f"Mapping URLs from {url}")
                map_result = await self._map_service.map(
                    url=url,
                    limit=limit,
                    max_depth=max_depth,
                )

                if not map_result.success:
                    yield CrawlEvent(
                        type="error",
                        error=f"Map failed: {map_result.error}",
                    )
                    return

                # Filter URLs
                urls_to_scrape = []
                for link in map_result.links:
                    if link.url in scraped_urls:
                        continue
                    if include_patterns and not self._matches_patterns(link.url, include_patterns):
                        continue
                    if exclude_patterns and self._matches_patterns(link.url, exclude_patterns):
                        continue
                    urls_to_scrape.append(link.url)

                total = len(urls_to_scrape)
                LOGGER.info(f"Found {total} URLs to scrape")

                yield CrawlEvent(
                    type="progress",
                    completed=0,
                    total=total,
                )

                # Scrape each URL
                completed = 0
                data = []
                errors = []

                for url_to_scrape in urls_to_scrape:
                    try:
                        result = await self._scrape_service.scrape(url_to_scrape)

                        if result.success and result.data:
                            data.append(result.data)

                            # Save to output directory
                            if output_dir:
                                self._save_page(output_dir, url_to_scrape, result.data)

                            yield CrawlEvent(
                                type="page",
                                url=url_to_scrape,
                                data=result.data,
                                completed=completed + 1,
                                total=total,
                            )
                        else:
                            errors.append(f"{url_to_scrape}: {result.error}")
                            yield CrawlEvent(
                                type="error",
                                url=url_to_scrape,
                                error=result.error,
                                completed=completed + 1,
                                total=total,
                            )

                    except Exception as e:
                        errors.append(f"{url_to_scrape}: {str(e)}")
                        LOGGER.error(f"Scrape failed for {url_to_scrape}: {e}")

                    completed += 1

                    yield CrawlEvent(
                        type="progress",
                        completed=completed,
                        total=total,
                    )

                # Final complete event
                yield CrawlEvent(
                    type="complete",
                    completed=completed,
                    total=total,
                )

        except Exception as e:
            LOGGER.error(f"Crawl failed: {e}")
            yield CrawlEvent(
                type="error",
                error=str(e),
            )

    def _matches_patterns(self, url: str, patterns: list[str]) -> bool:
        """Check if URL matches any pattern.

        Args:
            url: URL to check
            patterns: Patterns to match against

        Returns:
            True if URL matches any pattern
        """
        import fnmatch
        return any(fnmatch.fnmatch(url, pattern) for pattern in patterns)

    def _load_resume_state(self, output_dir: Path) -> set[str]:
        """Load URLs that have already been scraped.

        Args:
            output_dir: Output directory

        Returns:
            Set of already-scraped URLs
        """
        scraped = set()
        manifest_path = output_dir / "manifest.json"

        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
                scraped = set(manifest.get("scraped_urls", []))

        return scraped

    def _save_page(self, output_dir: Path, url: str, data) -> None:
        """Save scraped page to output directory.

        Args:
            output_dir: Output directory
            url: Source URL
            data: ScrapeData to save
        """
        from urllib.parse import urlparse
        import hashlib

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from URL
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_") or "index"
        filename = f"{path}.md"

        # Handle duplicates with hash suffix
        if (output_dir / filename).exists():
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
            filename = f"{path}_{url_hash}.md"

        # Save markdown
        if data.markdown:
            with open(output_dir / filename, "w") as f:
                # Add frontmatter
                f.write("---\n")
                f.write(f"source_url: {url}\n")
                if data.metadata and data.metadata.title:
                    f.write(f"title: {data.metadata.title}\n")
                f.write("---\n\n")
                f.write(data.markdown)

        # Update manifest
        manifest_path = output_dir / "manifest.json"
        manifest = {"scraped_urls": []}
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)

        manifest["scraped_urls"].append(url)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
```

### CLI Integration (`web_scraper/cli.py`)

Add a new `crawl` command:

```python
@cli.command()
@click.argument("url")
@click.option("--limit", default=100, help="Maximum pages to crawl")
@click.option("--depth", default=3, help="Maximum crawl depth")
@click.option("--include", multiple=True, help="URL patterns to include")
@click.option("--exclude", multiple=True, help="URL patterns to exclude")
@click.option("--output", "-o", type=click.Path(), required=True, help="Output directory")
@click.option("--resume", is_flag=True, help="Resume from previous crawl")
def crawl(url: str, limit: int, depth: int, include: tuple, exclude: tuple, output: str, resume: bool):
    """Crawl a website and save all pages.

    Examples:
        web-scraper crawl https://example.com --limit 50 --output corpus/
        web-scraper crawl https://example.com --output corpus/ --resume
    """
    import asyncio
    from pathlib import Path
    from web_scraper.crawl_service import CrawlService

    async def run():
        service = CrawlService()
        async for event in service.crawl(
            url=url,
            limit=limit,
            max_depth=depth,
            include_patterns=list(include) if include else None,
            exclude_patterns=list(exclude) if exclude else None,
            output_dir=Path(output),
            resume=resume,
        ):
            if event.type == "progress":
                click.echo(f"Progress: {event.completed}/{event.total}")
            elif event.type == "page":
                click.echo(f"Scraped: {event.url}")
            elif event.type == "error":
                click.echo(f"Error: {event.url}: {event.error}", err=True)
            elif event.type == "complete":
                click.echo(f"Complete: {event.completed}/{event.total} pages")

    asyncio.run(run())
```

---

## Unit Tests (`tests/unit/test_crawl_service.py`)

```python
"""Tests for crawl service."""

import pytest
from pathlib import Path
from web_scraper.crawl_service import CrawlService
from web_scraper.models import CrawlEvent


class TestCrawlService:
    """Tests for CrawlService."""

    @pytest.mark.asyncio
    async def test_crawl_yields_events(self, tmp_path):
        """Test that crawl yields events."""
        service = CrawlService()
        events = []
        async for event in service.crawl(
            "https://example.com",
            limit=5,
            output_dir=tmp_path,
        ):
            events.append(event)

        assert len(events) > 0
        assert any(e.type == "progress" for e in events)
        assert any(e.type == "complete" for e in events)

    @pytest.mark.asyncio
    async def test_crawl_saves_to_output_dir(self, tmp_path):
        """Test that crawl saves pages to output directory."""
        service = CrawlService()
        async for _ in service.crawl(
            "https://example.com",
            limit=2,
            output_dir=tmp_path,
        ):
            pass

        # Check that files were created
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) > 0

        # Check manifest exists
        assert (tmp_path / "manifest.json").exists()

    @pytest.mark.asyncio
    async def test_crawl_respects_limit(self, tmp_path):
        """Test that crawl respects page limit."""
        service = CrawlService()
        pages_scraped = 0
        async for event in service.crawl(
            "https://example.com",
            limit=3,
            output_dir=tmp_path,
        ):
            if event.type == "page":
                pages_scraped += 1

        assert pages_scraped <= 3

    def test_matches_patterns(self):
        """Test URL pattern matching."""
        service = CrawlService()
        assert service._matches_patterns("https://example.com/api/v1", ["*/api/*"])
        assert not service._matches_patterns("https://example.com/docs", ["*/api/*"])
```

---

## Verification Checklist

After implementation, verify:

- [ ] `python -c "from web_scraper.crawl_service import CrawlService"` works
- [ ] `pytest tests/unit/test_crawl_service.py -v` passes
- [ ] No `crawl4ai` imports in new files
- [ ] CLI command works: `web-scraper crawl https://example.com --limit 10 --output /tmp/test-corpus`
- [ ] Resume works: run twice with `--resume`

---

## Commit Message

When complete, commit with:

```
feat: add crawl command for full-site scraping

- Add CrawlService combining map + scrape pipeline (#19)
- Implement AsyncGenerator for streaming results
- Add progress reporting and resume capability (#20)
- Save scraped pages to output directory with manifest
- Support include/exclude URL patterns
- Add unit tests

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Next Steps

After Phase 4 is complete, proceed to Phase 5 (Batch operations) using issues #21-22.
