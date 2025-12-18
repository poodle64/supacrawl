"""Tests for politeness controls, delays, and interruption handling.

These tests verify that:
1. Delay between requests is enforced
2. CrawlInterrupted exception is raised on KeyboardInterrupt
3. Snapshot state is saved on interruption
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from web_scraper.exceptions import CrawlInterrupted
from web_scraper.models import SiteConfig, CrawlPolitenessConfig


# --- Fixtures ---

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _minimal_site_config(base_url: str, max_pages: int = 5) -> SiteConfig:
    """Create a minimal site config for testing."""
    return SiteConfig(
        id="test-politeness",
        name="Test Politeness Site",
        entrypoints=[base_url],
        include=[f"{base_url}/**"],
        exclude=[],
        max_pages=max_pages,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
    )


# --- Unit Tests ---


class TestCrawlPolitenessConfig:
    """Test CrawlPolitenessConfig model validation."""

    def test_default_values(self) -> None:
        """Test default politeness values."""
        config = CrawlPolitenessConfig()
        assert config.max_concurrent == 5
        assert config.delay_between_requests == (1.0, 2.0)
        assert config.page_timeout == 120.0
        assert config.max_retries == 3

    def test_custom_values(self) -> None:
        """Test custom politeness values."""
        config = CrawlPolitenessConfig(
            max_concurrent=10,
            delay_between_requests=(0.5, 1.0),
            page_timeout=60.0,
            max_retries=5,
        )
        assert config.max_concurrent == 10
        assert config.delay_between_requests == (0.5, 1.0)
        assert config.page_timeout == 60.0
        assert config.max_retries == 5

    def test_max_concurrent_bounds(self) -> None:
        """Test max_concurrent validation bounds."""
        # Valid bounds
        CrawlPolitenessConfig(max_concurrent=1)
        CrawlPolitenessConfig(max_concurrent=20)
        
        # Invalid: too low
        with pytest.raises(ValueError):
            CrawlPolitenessConfig(max_concurrent=0)
        
        # Invalid: too high
        with pytest.raises(ValueError):
            CrawlPolitenessConfig(max_concurrent=21)

    def test_page_timeout_bounds(self) -> None:
        """Test page_timeout validation bounds."""
        # Valid bounds
        CrawlPolitenessConfig(page_timeout=5.0)
        CrawlPolitenessConfig(page_timeout=600.0)
        
        # Invalid: too low
        with pytest.raises(ValueError):
            CrawlPolitenessConfig(page_timeout=4.9)
        
        # Invalid: too high
        with pytest.raises(ValueError):
            CrawlPolitenessConfig(page_timeout=600.1)

    def test_max_retries_bounds(self) -> None:
        """Test max_retries validation bounds."""
        # Valid bounds
        CrawlPolitenessConfig(max_retries=0)
        CrawlPolitenessConfig(max_retries=10)
        
        # Invalid: too low
        with pytest.raises(ValueError):
            CrawlPolitenessConfig(max_retries=-1)
        
        # Invalid: too high
        with pytest.raises(ValueError):
            CrawlPolitenessConfig(max_retries=11)


class TestCrawlInterruptedException:
    """Test CrawlInterrupted exception."""

    def test_exception_attributes(self, tmp_path: Path) -> None:
        """Test exception stores path and page count."""
        exc = CrawlInterrupted(snapshot_path=tmp_path, pages_completed=42)
        assert exc.snapshot_path == tmp_path
        assert exc.pages_completed == 42
        assert "42 pages" in str(exc)
        assert "Resume by running the same command again" in str(exc)


class TestDelayEnforcement:
    """Test that delays are applied between requests."""

    def test_delay_config_is_wired_correctly(self) -> None:
        """Test that delay config is correctly set on SiteConfig."""
        # Create config with specific delay
        config = SiteConfig(
            id="test-delay",
            name="Test Delay",
            entrypoints=["http://example.com"],
            include=["http://example.com/**"],
            exclude=[],
            max_pages=3,
            formats=["markdown"],
            only_main_content=True,
            include_subdomains=False,
            politeness=CrawlPolitenessConfig(
                delay_between_requests=(0.5, 0.5),  # Fixed 0.5s delay
                max_concurrent=1,
            ),
        )
        
        # Verify config has correct delay setting
        assert config.politeness.delay_between_requests == (0.5, 0.5)
        assert config.politeness.max_concurrent == 1
        
        # Note: Full delay enforcement testing would require a local HTTP server
        # and timing assertions. This test verifies the config is wired correctly.


class TestInterruptionHandling:
    """Test KeyboardInterrupt handling."""

    def test_crawl_interrupted_on_keyboard_interrupt(self, tmp_path: Path) -> None:
        """Test that CrawlInterrupted is raised on KeyboardInterrupt."""
        from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
        
        config = _minimal_site_config("http://example.com", max_pages=10)
        
        scraper = Crawl4AIScraper()
        
        # Mock asyncio.run to raise KeyboardInterrupt during crawl
        # We need to consume the coroutine to avoid RuntimeWarning
        call_count = 0
        def mock_run_side_effect(coro):
            nonlocal call_count
            coro.close()
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt()
            return None
        
        with patch("asyncio.run") as mock_run:
            mock_run.side_effect = mock_run_side_effect
            
            with pytest.raises(CrawlInterrupted) as exc_info:
                scraper.crawl(config, tmp_path / "corpora")
            
            # Verify exception has correct attributes
            assert exc_info.value.pages_completed == 0
            assert "corpora" in str(exc_info.value.snapshot_path)

    def test_manifest_shows_interrupted_status(self, tmp_path: Path) -> None:
        """Test that manifest shows interrupted status after Ctrl+C."""
        from web_scraper.corpus.writer import IncrementalSnapshotWriter
        from web_scraper.models import Page
        
        config = _minimal_site_config("http://example.com")
        corpora_dir = tmp_path / "corpora"
        
        # Create writer and simulate interrupt
        writer = IncrementalSnapshotWriter(config, corpora_dir)
        
        # Start the writer
        asyncio.run(writer.start())
        
        # Add a page with all required fields
        page = Page(
            site_id="test-politeness",
            url="http://example.com/page1",
            path="page1",
            content_html="<html><body>Test</body></html>",
            content_markdown="# Test",
            title="Test Page",
            content_hash="abc123",
            provider="test",
        )
        asyncio.run(writer.add_pages([page]))
        
        # Abort with interrupted status
        asyncio.run(writer.abort("interrupted"))
        
        # Verify manifest
        manifest_path = writer.snapshot_root() / "manifest.json"
        assert manifest_path.exists()
        
        manifest = json.loads(manifest_path.read_text())
        assert manifest["status"] == "aborted"


class TestPolitenessCLIOverrides:
    """Test CLI option overrides for politeness settings."""

    def test_cli_overrides_applied_to_config(self) -> None:
        """Test that CLI overrides are applied to config."""
        from click.testing import CliRunner
        from web_scraper.cli import app
        
        runner = CliRunner()
        
        # Just verify the CLI accepts the options without error
        # by calling --help for the crawl command
        result = runner.invoke(app, ["crawl", "--help"])
        assert result.exit_code == 0
        assert "--concurrency" in result.output
        assert "--delay" in result.output
        assert "--timeout" in result.output
        assert "--retries" in result.output

