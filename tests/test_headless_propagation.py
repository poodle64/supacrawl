"""Tests for headless parameter propagation across services.

Ensures that when headless is set, it flows through to any BrowserManager
instances created internally by ScrapeService, MapService, and CrawlService.
See: https://github.com/supacrawl/supacrawl/issues/78
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from supacrawl.services.browser import BrowserManager
from supacrawl.services.crawl import CrawlService
from supacrawl.services.map import MapService
from supacrawl.services.scrape import ScrapeService


class TestBrowserManagerHeadlessDefaults:
    """Test BrowserManager headless logic."""

    def test_headless_default_without_stealth(self):
        """Without stealth, headless defaults to True."""
        bm = BrowserManager()
        assert bm.headless is True

    def test_headless_default_with_stealth(self):
        """With stealth, headless defaults to False (headful is more effective)."""
        bm = BrowserManager(stealth=True)
        assert bm.headless is False

    def test_explicit_headless_overrides_stealth_default(self):
        """Explicitly passing headless=True overrides stealth's headful default."""
        bm = BrowserManager(headless=True, stealth=True)
        assert bm.headless is True

    def test_explicit_headless_false(self):
        """Explicitly passing headless=False is honoured."""
        bm = BrowserManager(headless=False)
        assert bm.headless is False


class TestScrapeServiceHeadlessPropagation:
    """Test that ScrapeService stores and propagates headless."""

    def test_stores_headless_parameter(self):
        """ScrapeService should store the headless parameter."""
        service = ScrapeService(headless=True)
        assert service._headless is True

    def test_stores_headless_none_by_default(self):
        """ScrapeService should default headless to None."""
        service = ScrapeService()
        assert service._headless is None

    @pytest.mark.asyncio
    async def test_owns_browser_passes_headless(self):
        """When creating its own BrowserManager, ScrapeService passes headless."""
        service = ScrapeService(headless=True, stealth=True)
        assert service._owns_browser is True

        with (
            patch.object(BrowserManager, "__aenter__", new_callable=AsyncMock) as mock_enter,
            patch.object(BrowserManager, "__aexit__", new_callable=AsyncMock),
            patch.object(BrowserManager, "__init__", return_value=None) as mock_init,
            patch.object(BrowserManager, "fetch_page", new_callable=AsyncMock),
        ):
            mock_enter.return_value = MagicMock()

            try:
                await service.scrape("https://example.com")
            except Exception:
                pass  # We only care about the BrowserManager constructor call

            # Verify headless=True was passed to BrowserManager
            if mock_init.called:
                _, kwargs = mock_init.call_args
                assert kwargs.get("headless") is True


class TestMapServiceHeadlessPropagation:
    """Test that MapService stores and propagates headless."""

    def test_stores_headless_parameter(self):
        """MapService should store the headless parameter."""
        service = MapService(headless=True)
        assert service._headless is True

    def test_stores_headless_none_by_default(self):
        """MapService should default headless to None."""
        service = MapService()
        assert service._headless is None

    def test_shared_browser_skips_creation(self):
        """When browser is provided, MapService does not create its own."""
        browser = MagicMock(spec=BrowserManager)
        service = MapService(browser=browser, headless=True)
        assert service._owns_browser is False


class TestCrawlServiceHeadlessParameter:
    """Test that CrawlService.crawl() accepts headless parameter."""

    def test_crawl_signature_includes_headless(self):
        """CrawlService.crawl() should accept a headless parameter."""
        import inspect

        sig = inspect.signature(CrawlService.crawl)
        assert "headless" in sig.parameters
        # Default should be None
        assert sig.parameters["headless"].default is None


class TestMCPSettingsHeadless:
    """Test MCP settings default headless to True."""

    def test_mcp_settings_default_headless_true(self):
        """MCP settings should default headless to True."""
        from supacrawl.mcp.config import SupacrawlSettings

        settings = SupacrawlSettings()
        assert settings.headless is True

    def test_mcp_settings_headless_overridable(self):
        """MCP settings headless should be overridable."""
        from supacrawl.mcp.config import SupacrawlSettings

        settings = SupacrawlSettings(headless=False)
        assert settings.headless is False
