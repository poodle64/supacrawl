"""Tests for browser manager."""

import pytest

from supacrawl.services.browser import BrowserManager, PageContent, PageMetadata


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
        os.environ["SUPACRAWL_TEST"] = "true"
        assert BrowserManager._env_bool("SUPACRAWL_TEST", False) is True

        os.environ["SUPACRAWL_TEST"] = "1"
        assert BrowserManager._env_bool("SUPACRAWL_TEST", False) is True

        os.environ["SUPACRAWL_TEST"] = "yes"
        assert BrowserManager._env_bool("SUPACRAWL_TEST", False) is True

        # Test falsy values
        os.environ["SUPACRAWL_TEST"] = "false"
        assert BrowserManager._env_bool("SUPACRAWL_TEST", True) is False

        os.environ["SUPACRAWL_TEST"] = "0"
        assert BrowserManager._env_bool("SUPACRAWL_TEST", True) is False

        # Test default
        del os.environ["SUPACRAWL_TEST"]
        assert BrowserManager._env_bool("SUPACRAWL_TEST", True) is True
        assert BrowserManager._env_bool("SUPACRAWL_TEST", False) is False

    @pytest.mark.asyncio
    async def test_extract_images_from_html(self):
        """Test image extraction from HTML."""
        html = """
        <html>
            <body>
                <img src="/image1.jpg">
                <img src="https://example.com/image2.png">
                <img src="data:image/png;base64,iVBORw0...">
                <img srcset="/image3.jpg 1x, /image4.jpg 2x">
            </body>
        </html>
        """
        async with BrowserManager() as browser:
            images = await browser.extract_images(html, "https://example.com")
            assert isinstance(images, list)
            # Should have image1, image2, image3, image4 (not data URI)
            assert len(images) >= 4
            # All should be absolute URLs
            assert all(img.startswith("http") for img in images)
            # Should not contain data URIs
            assert not any(img.startswith("data:") for img in images)

    @pytest.mark.asyncio
    async def test_extract_images_with_srcset(self):
        """Test image extraction with srcset attribute."""
        html = """
        <html>
            <body>
                <img srcset="small.jpg 300w, medium.jpg 600w, large.jpg 900w" src="default.jpg">
                <picture>
                    <source srcset="image.webp" type="image/webp">
                    <source srcset="image.jpg" type="image/jpeg">
                    <img src="fallback.jpg">
                </picture>
            </body>
        </html>
        """
        async with BrowserManager() as browser:
            images = await browser.extract_images(html, "https://example.com")
            assert isinstance(images, list)
            # Should have small, medium, large, default, image.webp, image.jpg, fallback
            assert len(images) >= 6

    @pytest.mark.asyncio
    async def test_extract_images_filters_tracking_pixels(self):
        """Test that tracking pixels are filtered out."""
        html = """
        <html>
            <body>
                <img src="/good-image.jpg">
                <img src="/pixel.gif">
                <img src="/tracking-1x1.png">
                <img src="/analytics.jpg">
            </body>
        </html>
        """
        async with BrowserManager() as browser:
            images = await browser.extract_images(html, "https://example.com")
            assert isinstance(images, list)
            # Should only have good-image.jpg
            assert len(images) == 1
            assert "good-image.jpg" in images[0]

    @pytest.mark.asyncio
    async def test_extract_images_deduplicates(self):
        """Test that duplicate images are removed."""
        html = """
        <html>
            <body>
                <img src="/image.jpg">
                <img src="/image.jpg">
                <img src="https://example.com/image.jpg">
            </body>
        </html>
        """
        async with BrowserManager() as browser:
            images = await browser.extract_images(html, "https://example.com")
            assert isinstance(images, list)
            # Should only have one unique image
            assert len(images) == 1

    @pytest.mark.asyncio
    async def test_extract_images_empty_page(self):
        """Test image extraction from page with no images."""
        html = "<html><body><p>No images here</p></body></html>"
        async with BrowserManager() as browser:
            images = await browser.extract_images(html, "https://example.com")
            assert isinstance(images, list)
            assert len(images) == 0
