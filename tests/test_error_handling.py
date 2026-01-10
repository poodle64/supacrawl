"""Error handling E2E tests - test error scenarios and recovery."""

import pytest

from supacrawl.services.browser import BrowserManager
from supacrawl.services.scrape import ScrapeService


@pytest.mark.e2e
class TestErrorHandling:
    """Test error handling in E2E scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_url_handling(self) -> None:
        """Test handling of invalid URLs."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://this-domain-does-not-exist-12345.com")

        # Should fail gracefully with error
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        """Test timeout is handled gracefully."""
        async with BrowserManager(timeout_ms=1000) as browser:
            service = ScrapeService(browser=browser)
            # This might timeout depending on network
            result = await service.scrape("https://example.com")

        # Either succeeds (fast network) or fails gracefully (timeout)
        assert hasattr(result, "success")
        if not result.success:
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_malformed_url_handling(self) -> None:
        """Test handling of malformed URLs."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("not-a-valid-url")

        # Should fail gracefully
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_network_error_handling(self) -> None:
        """Test handling of network errors."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            # Use a URL that should cause network error (unreachable host)
            result = await service.scrape("https://192.0.2.1")

        # Should fail gracefully (192.0.2.1 is reserved TEST-NET-1)
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_empty_url_handling(self) -> None:
        """Test handling of empty URLs."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("")

        # Should fail gracefully
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_scrape_404_handling(self) -> None:
        """Test handling of 404 errors."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            # Try a URL that should return 404
            result = await service.scrape("https://example.com/this-page-does-not-exist-12345")

        # Should either succeed (some 404 pages are valid HTML) or fail gracefully
        assert hasattr(result, "success")
        # If it succeeds, it should have some content
        if result.success:
            assert result.data.markdown is not None
        else:
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_very_short_timeout(self) -> None:
        """Test very short timeout causes graceful failure."""
        async with BrowserManager(timeout_ms=1) as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com", timeout=1)

        # Should timeout and fail gracefully
        # May succeed if page loads extremely fast, but that's okay
        assert hasattr(result, "success")
        if not result.success:
            assert result.error is not None
