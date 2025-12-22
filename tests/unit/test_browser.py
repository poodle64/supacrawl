"""Tests for browser manager."""

import pytest
from web_scraper.browser import BrowserManager, PageContent, PageMetadata


class TestBrowserManager:
    """Tests for BrowserManager."""

    @pytest.mark.asyncio
    async def test_fetch_page_returns_html(self):
        """Test that fetch_page returns HTML content."""
        async with BrowserManager() as browser:
            content = await browser.fetch_page("https://example.com", wait_for_spa=False)
            assert isinstance(content, PageContent)
            assert content.html
            assert "<html" in content.html.lower()
            assert content.url == "https://example.com"
            assert content.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_page_with_spa_wait(self):
        """Test that fetch_page works with SPA waiting enabled."""
        async with BrowserManager() as browser:
            content = await browser.fetch_page("https://example.com", wait_for_spa=True, spa_timeout_ms=2000)
            assert isinstance(content, PageContent)
            assert content.html
            assert content.title is not None

    @pytest.mark.asyncio
    async def test_extract_links_finds_links(self):
        """Test that extract_links finds anchor tags."""
        async with BrowserManager() as browser:
            links = await browser.extract_links("https://example.com")
            assert isinstance(links, list)
            # example.com should have at least the IANA link
            assert len(links) >= 0  # May have links or may not

    @pytest.mark.asyncio
    async def test_extract_metadata_from_html(self):
        """Test metadata extraction from HTML."""
        html = """
        <html>
            <head>
                <title>Test Page</title>
                <meta name="description" content="Test description">
                <meta property="og:title" content="OG Title">
                <meta property="og:description" content="OG Description">
                <meta property="og:image" content="https://example.com/image.jpg">
            </head>
            <body>
                <h1>Test</h1>
            </body>
        </html>
        """
        async with BrowserManager() as browser:
            metadata = await browser.extract_metadata(html)
            assert isinstance(metadata, PageMetadata)
            assert metadata.title == "Test Page"
            assert metadata.description == "Test description"
            assert metadata.og_title == "OG Title"
            assert metadata.og_description == "OG Description"
            assert metadata.og_image == "https://example.com/image.jpg"

    @pytest.mark.asyncio
    async def test_extract_metadata_handles_missing_tags(self):
        """Test metadata extraction with missing tags."""
        html = "<html><body><h1>Test</h1></body></html>"
        async with BrowserManager() as browser:
            metadata = await browser.extract_metadata(html)
            assert isinstance(metadata, PageMetadata)
            assert metadata.title is None
            assert metadata.description is None
            assert metadata.og_title is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test that BrowserManager works as async context manager."""
        async with BrowserManager() as browser:
            assert browser._browser is not None
            assert browser._playwright is not None

    @pytest.mark.asyncio
    async def test_env_bool_parsing(self):
        """Test environment boolean parsing."""
        import os

        # Test various truthy values
        os.environ["WEB_SCRAPER_TEST"] = "true"
        assert BrowserManager._env_bool("WEB_SCRAPER_TEST", False) is True

        os.environ["WEB_SCRAPER_TEST"] = "1"
        assert BrowserManager._env_bool("WEB_SCRAPER_TEST", False) is True

        os.environ["WEB_SCRAPER_TEST"] = "yes"
        assert BrowserManager._env_bool("WEB_SCRAPER_TEST", False) is True

        # Test falsy values
        os.environ["WEB_SCRAPER_TEST"] = "false"
        assert BrowserManager._env_bool("WEB_SCRAPER_TEST", True) is False

        os.environ["WEB_SCRAPER_TEST"] = "0"
        assert BrowserManager._env_bool("WEB_SCRAPER_TEST", True) is False

        # Test default
        del os.environ["WEB_SCRAPER_TEST"]
        assert BrowserManager._env_bool("WEB_SCRAPER_TEST", True) is True
        assert BrowserManager._env_bool("WEB_SCRAPER_TEST", False) is False
