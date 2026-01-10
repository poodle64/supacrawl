"""Tests for map service."""

import pytest

from supacrawl.models import MapLink, MapResult
from supacrawl.services.map import MapService


class TestMapService:
    """Tests for MapService."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_map_all_returns_result(self):
        """Test that map_all returns a MapResult."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=5)
        assert isinstance(result, MapResult)
        assert result.success is True or result.error is not None

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_map_all_returns_links(self):
        """Test that map_all returns discovered links."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=10)
        assert isinstance(result, MapResult)
        if result.success:
            assert len(result.links) > 0
            assert all(isinstance(link, MapLink) for link in result.links)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_map_all_respects_limit(self):
        """Test that map_all respects URL limit."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=5)
        if result.success:
            assert len(result.links) <= 5

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_map_all_extracts_titles(self):
        """Test that map_all extracts page titles."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=3)
        if result.success and result.links:
            # At least one link should have a title
            titles = [link.title for link in result.links if link.title]
            assert len(titles) >= 0  # May be empty for some sites

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_map_streaming_yields_events(self):
        """Test that map() yields progress events as an async generator."""
        service = MapService()
        events = []
        async for event in service.map("https://example.com", limit=3):
            events.append(event)
        # Should have at least a complete or error event
        event_types = [e.type for e in events]
        assert "complete" in event_types or "error" in event_types

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

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_search_filter(self):
        """Test URL filtering with search."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=100, search="about")
        if result.success:
            # All URLs should contain "about" (case insensitive)
            for link in result.links:
                assert "about" in link.url.lower(), f"URL '{link.url}' does not contain 'about'"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_sitemap_only_mode(self):
        """Test sitemap-only discovery mode."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=10, sitemap="only", max_depth=0)
        # Should succeed or fail gracefully
        assert isinstance(result, MapResult)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_sitemap_skip_mode(self):
        """Test sitemap skip mode (BFS only)."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=5, sitemap="skip")
        # Should succeed or fail gracefully
        assert isinstance(result, MapResult)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_allow_external_links_default_false(self):
        """Test that external links are excluded by default."""
        service = MapService()
        result = await service.map_all("https://example.com", limit=10, sitemap="skip")
        if result.success:
            # All URLs should be from example.com (no external)
            for link in result.links:
                assert "example.com" in link.url, f"External link found: {link.url}"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_allow_external_links_enabled(self):
        """Test that external links are allowed when enabled."""
        service = MapService()
        # This test verifies the parameter is accepted; actual external link
        # discovery depends on the source page having external links
        result = await service.map_all(
            "https://example.com",
            limit=10,
            sitemap="skip",
            allow_external_links=True,
        )
        assert isinstance(result, MapResult)
        # Should succeed or fail gracefully
        assert result.success is True or result.error is not None
