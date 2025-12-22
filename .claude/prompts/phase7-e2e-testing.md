# Phase 7: End-to-End Testing

## Context

You are implementing Phase 7 of the Firecrawl-parity rebuild for the web-scraper project. This phase creates comprehensive E2E tests to validate the complete Playwright-based scraping stack.

**Branch:** `refactor/firecrawl-parity-v2`
**Depends On:** Phase 6 (Crawl4AI cleanup complete)

## Phase 7 Goals

Create E2E tests that:
1. Test the complete scraping pipeline (map → scrape → crawl → batch)
2. Validate output format matches Firecrawl
3. Test against real websites (with mocking for CI)
4. Test CLI commands end-to-end
5. Ensure resume/recovery works correctly

---

## Test Categories

### Category 1: CLI Command E2E Tests

Test each CLI command against real websites:

```python
"""E2E tests for CLI commands."""

import subprocess
import json
from pathlib import Path
import pytest


class TestMapCommand:
    """E2E tests for map-url command."""

    def test_map_url_returns_urls(self, tmp_path):
        """Test map-url discovers URLs."""
        result = subprocess.run(
            ["web-scraper", "map-url", "https://example.com", "--limit", "5"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "https://" in result.stdout

    def test_map_url_json_output(self, tmp_path):
        """Test map-url JSON output format."""
        output_file = tmp_path / "map.json"
        result = subprocess.run(
            ["web-scraper", "map-url", "https://example.com",
             "--limit", "3", "--output", str(output_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "links" in data or isinstance(data, list)


class TestScrapeCommand:
    """E2E tests for scrape-url command."""

    def test_scrape_url_returns_markdown(self):
        """Test scrape-url returns markdown content."""
        result = subprocess.run(
            ["web-scraper", "scrape-url", "https://example.com"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should contain some markdown
        assert "#" in result.stdout or "Example" in result.stdout

    def test_scrape_url_with_output(self, tmp_path):
        """Test scrape-url saves to file."""
        output_file = tmp_path / "page.md"
        result = subprocess.run(
            ["web-scraper", "scrape-url", "https://example.com",
             "--output", str(output_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert len(content) > 0


class TestCrawlCommand:
    """E2E tests for crawl-url command."""

    def test_crawl_creates_corpus(self, tmp_path):
        """Test crawl-url creates corpus directory."""
        output_dir = tmp_path / "corpus"
        result = subprocess.run(
            ["web-scraper", "crawl-url", "https://example.com",
             "--limit", "2", "--output", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0
        assert output_dir.exists()
        # Should have at least one markdown file
        md_files = list(output_dir.rglob("*.md"))
        assert len(md_files) >= 1

    def test_crawl_creates_manifest(self, tmp_path):
        """Test crawl-url creates manifest.json."""
        output_dir = tmp_path / "corpus"
        result = subprocess.run(
            ["web-scraper", "crawl-url", "https://example.com",
             "--limit", "2", "--output", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0
        manifest_files = list(output_dir.rglob("manifest.json"))
        assert len(manifest_files) >= 1


class TestBatchCommand:
    """E2E tests for batch-scrape command."""

    def test_batch_scrape_from_file(self, tmp_path):
        """Test batch-scrape processes URL file."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://example.com\nhttps://example.org\n")

        output_dir = tmp_path / "batch"
        result = subprocess.run(
            ["web-scraper", "batch-scrape", str(urls_file),
             "--concurrency", "2", "--output", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0
        assert output_dir.exists()
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 1
```

---

### Category 2: Firecrawl Parity Tests

Compare output against Firecrawl to ensure compatibility:

```python
"""Firecrawl parity tests."""

import pytest
from web_scraper.scrape_service import ScrapeService
from web_scraper.browser import BrowserManager


class TestFirecrawlParity:
    """Test output matches Firecrawl format."""

    @pytest.mark.asyncio
    async def test_scrape_result_structure(self):
        """Test ScrapeResult matches Firecrawl structure."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com")

        assert hasattr(result, "success")
        assert hasattr(result, "data")

        if result.success:
            assert hasattr(result.data, "markdown")
            assert hasattr(result.data, "metadata")
            assert hasattr(result.data.metadata, "title")
            assert hasattr(result.data.metadata, "source_url")

    @pytest.mark.asyncio
    async def test_map_result_structure(self):
        """Test MapResult matches Firecrawl structure."""
        from web_scraper.map_service import MapService

        async with BrowserManager() as browser:
            service = MapService(browser=browser)
            result = await service.map("https://example.com", limit=5)

        assert hasattr(result, "success")
        assert hasattr(result, "links")

        if result.success and result.links:
            link = result.links[0]
            assert hasattr(link, "url")
            # Optional fields
            assert hasattr(link, "title")

    @pytest.mark.asyncio
    async def test_markdown_quality(self):
        """Test markdown output quality."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com")

        assert result.success
        markdown = result.data.markdown

        # Basic quality checks
        assert len(markdown) > 100  # Not empty
        assert "Example Domain" in markdown  # Expected content
        assert "```" not in markdown or markdown.count("```") % 2 == 0  # Balanced code blocks
```

---

### Category 3: Pipeline Integration Tests

Test the complete pipeline flow:

```python
"""Pipeline integration tests."""

import pytest
from web_scraper.browser import BrowserManager
from web_scraper.map_service import MapService
from web_scraper.scrape_service import ScrapeService
from web_scraper.crawl_service import CrawlService
from web_scraper.batch_service import BatchService


class TestCompletePipeline:
    """Test complete scraping pipeline."""

    @pytest.mark.asyncio
    async def test_map_then_scrape(self):
        """Test map discovery followed by scraping."""
        async with BrowserManager() as browser:
            # Map to discover URLs
            map_service = MapService(browser=browser)
            map_result = await map_service.map("https://example.com", limit=3)

            assert map_result.success
            assert len(map_result.links) > 0

            # Scrape first discovered URL
            scrape_service = ScrapeService(browser=browser)
            url = map_result.links[0].url
            scrape_result = await scrape_service.scrape(url)

            assert scrape_result.success
            assert scrape_result.data.markdown

    @pytest.mark.asyncio
    async def test_crawl_streaming(self):
        """Test crawl service streaming."""
        service = CrawlService()
        events = []

        async for event in service.crawl(
            url="https://example.com",
            limit=2,
        ):
            events.append(event)

        # Should have progress and page events
        event_types = [e.type for e in events]
        assert "progress" in event_types or "page" in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_batch_concurrent(self):
        """Test batch service concurrency."""
        service = BatchService()
        urls = ["https://example.com", "https://example.org"]
        items = []

        async for event in service.batch_scrape(urls, concurrency=2):
            if event.type == "item":
                items.append(event.item)

        assert len(items) == 2
        # At least one should succeed
        assert any(item.success for item in items)
```

---

### Category 4: Error Handling Tests

Test error scenarios:

```python
"""Error handling E2E tests."""

import pytest
from web_scraper.scrape_service import ScrapeService
from web_scraper.browser import BrowserManager


class TestErrorHandling:
    """Test error handling in E2E scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_url_handling(self):
        """Test handling of invalid URLs."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://this-domain-does-not-exist-12345.com")

        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test timeout is handled gracefully."""
        async with BrowserManager(timeout_ms=1000) as browser:
            service = ScrapeService(browser=browser)
            # This might timeout depending on network
            result = await service.scrape("https://example.com")

        # Either succeeds or fails gracefully
        assert hasattr(result, "success")
        if not result.success:
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self):
        """Test batch handles partial failures."""
        service = BatchService()
        urls = [
            "https://example.com",  # Should succeed
            "https://invalid-url-12345.com",  # Should fail
        ]

        result = await service.batch_scrape_to_result(urls, concurrency=2)

        assert result.completed == 2
        assert result.successful >= 1
        assert result.failed >= 1
```

---

### Category 5: Resume and Recovery Tests

Test crawl resume functionality:

```python
"""Resume and recovery tests."""

import pytest
from pathlib import Path
from web_scraper.crawl_service import CrawlService


class TestResumeRecovery:
    """Test resume and recovery functionality."""

    @pytest.mark.asyncio
    async def test_crawl_creates_manifest(self, tmp_path):
        """Test crawl creates resumable manifest."""
        output_dir = tmp_path / "corpus"
        service = CrawlService()

        async for event in service.crawl(
            url="https://example.com",
            limit=2,
            output_dir=output_dir,
        ):
            pass

        manifest = output_dir / "manifest.json"
        assert manifest.exists()

    @pytest.mark.asyncio
    async def test_crawl_resume_skips_completed(self, tmp_path):
        """Test resume skips already completed URLs."""
        output_dir = tmp_path / "corpus"
        service = CrawlService()

        # First crawl
        first_events = []
        async for event in service.crawl(
            url="https://example.com",
            limit=2,
            output_dir=output_dir,
        ):
            first_events.append(event)

        # Resume crawl (should skip completed)
        resume_events = []
        async for event in service.crawl(
            url="https://example.com",
            limit=2,
            output_dir=output_dir,
            resume=True,
        ):
            resume_events.append(event)

        # Resume should have fewer page events (skipped completed)
        first_pages = [e for e in first_events if e.type == "page"]
        resume_pages = [e for e in resume_events if e.type == "page"]

        # Either no new pages or same pages (already complete)
        assert len(resume_pages) <= len(first_pages)
```

---

## Test File Structure

Create these test files:

```
tests/
├── e2e/
│   ├── __init__.py
│   ├── test_cli_commands.py      # Category 1
│   ├── test_firecrawl_parity.py  # Category 2
│   ├── test_pipeline.py          # Category 3
│   ├── test_error_handling.py    # Category 4
│   └── test_resume.py            # Category 5
└── fixtures/
    └── e2e/
        └── urls.txt              # Test URLs file
```

---

## Test Configuration

### `conftest.py` additions

```python
"""E2E test fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def test_urls():
    """Common test URLs."""
    return [
        "https://example.com",
        "https://example.org",
    ]


@pytest.fixture
def urls_file(tmp_path, test_urls):
    """Create temporary URLs file."""
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("\n".join(test_urls))
    return urls_file


# Increase timeout for E2E tests
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
```

---

## Running E2E Tests

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run with increased timeout
pytest tests/e2e/ -v --timeout=120

# Run specific category
pytest tests/e2e/test_cli_commands.py -v

# Skip slow tests
pytest tests/e2e/ -v -m "not slow"

# Run with verbose output
pytest tests/e2e/ -v -s
```

---

## Verification Checklist

After implementation:

- [ ] All CLI command tests pass
- [ ] Firecrawl parity tests pass
- [ ] Pipeline integration tests pass
- [ ] Error handling tests pass
- [ ] Resume/recovery tests pass
- [ ] No crawl4ai references in test files
- [ ] Tests complete within 5 minutes

---

## Commit Message

When complete, commit with:

```
test: add comprehensive E2E tests for scraping stack

- Add CLI command E2E tests
- Add Firecrawl parity tests
- Add pipeline integration tests
- Add error handling tests
- Add resume/recovery tests
- Create test fixtures

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Completion

After Phase 7, the Firecrawl-parity implementation is complete with:

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ | Core Infrastructure (Browser, Converter) |
| 2 | ✅ | Map Command |
| 3 | ✅ | Scrape Command |
| 4 | ✅ | Crawl Command |
| 5 | ✅ | Batch Operations |
| 6 | ✅ | Crawl4AI Cleanup |
| 7 | ✅ | E2E Testing |

The branch can now be merged to main.
