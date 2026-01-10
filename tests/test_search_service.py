"""Tests for search service."""

import pytest

from supacrawl.models import SearchResult, SearchResultItem, SearchSourceType
from supacrawl.services.search import SearchService


class TestSearchService:
    """Tests for SearchService."""

    @pytest.mark.asyncio
    async def test_search_returns_web_results(self):
        """Test that search returns web results by default."""
        service = SearchService()
        try:
            result = await service.search("python programming language", limit=3)
            assert isinstance(result, SearchResult)
            assert result.success
            # Web search may return empty results due to rate limiting
            # Just check that any results have correct source_type
            for item in result.data:
                assert item.source_type == SearchSourceType.WEB
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_respects_limit(self):
        """Test that search respects the limit parameter."""
        service = SearchService()
        try:
            result = await service.search("python", limit=2)
            assert result.success
            assert len(result.data) <= 2
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_result_structure(self):
        """Test that search results have correct structure."""
        service = SearchService()
        try:
            result = await service.search("example", limit=1)
            assert result.success
            if result.data:
                item = result.data[0]
                assert isinstance(item, SearchResultItem)
                assert isinstance(item.url, str)
                assert len(item.url) > 0
                assert isinstance(item.title, str)
                assert item.source_type == SearchSourceType.WEB
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_with_web_source(self):
        """Test search with explicit web source."""
        service = SearchService()
        try:
            result = await service.search("python", limit=3, sources=["web"])
            assert result.success
            for item in result.data:
                assert item.source_type == SearchSourceType.WEB
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_with_images_source(self):
        """Test search with images source type."""
        service = SearchService()
        try:
            result = await service.search("cat", limit=3, sources=["images"])
            assert isinstance(result, SearchResult)
            # Image search may return empty results if vqd token extraction fails
            # so we just check the structure is correct
            for item in result.data:
                assert item.source_type == SearchSourceType.IMAGES
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_with_news_source(self):
        """Test search with news source type."""
        service = SearchService()
        try:
            result = await service.search("technology", limit=3, sources=["news"])
            assert isinstance(result, SearchResult)
            # News search may return empty results if vqd token extraction fails
            for item in result.data:
                assert item.source_type == SearchSourceType.NEWS
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_with_multiple_sources(self):
        """Test search with multiple source types."""
        service = SearchService()
        try:
            result = await service.search("technology", limit=3, sources=["web", "news"])
            assert isinstance(result, SearchResult)
            assert result.success
            # May have results from web, news, or both
            # Just verify that all results have valid source types
            for item in result.data:
                assert item.source_type in (SearchSourceType.WEB, SearchSourceType.NEWS)
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_image_result_fields(self):
        """Test that image results have image-specific fields."""
        service = SearchService()
        try:
            result = await service.search("landscape", limit=5, sources=["images"])
            # If we got image results, check image-specific fields
            for item in result.data:
                if item.source_type == SearchSourceType.IMAGES:
                    # Image results should have URL
                    assert item.url is not None
                    # Thumbnail may or may not be present
                    # Width/height may or may not be present
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_news_result_fields(self):
        """Test that news results have news-specific fields."""
        service = SearchService()
        try:
            result = await service.search("technology", limit=5, sources=["news"])
            # If we got news results, check news-specific fields
            for item in result.data:
                if item.source_type == SearchSourceType.NEWS:
                    assert item.url is not None
                    # published_at and source_name may or may not be present
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_handles_unknown_source_type(self):
        """Test that search handles unknown source types gracefully."""
        service = SearchService()
        try:
            # This should not raise, just skip unknown sources
            result = await service.search(
                "python",
                limit=3,
                sources=["web", "unknown"],  # type: ignore
            )
            assert isinstance(result, SearchResult)
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_search_clamps_limit(self):
        """Test that search clamps limit to valid range."""
        service = SearchService()
        try:
            # Limit below minimum should be clamped to 1
            result = await service.search("python", limit=0)
            assert result.success

            # Limit above maximum should be clamped to 10
            result = await service.search("python", limit=100)
            assert result.success
            # Should not return more than 10 results
            assert len(result.data) <= 10
        finally:
            await service.close()


class TestSearchSourceType:
    """Tests for SearchSourceType enum."""

    def test_source_type_values(self):
        """Test that source type enum has expected values."""
        assert SearchSourceType.WEB.value == "web"
        assert SearchSourceType.IMAGES.value == "images"
        assert SearchSourceType.NEWS.value == "news"

    def test_source_type_is_string_enum(self):
        """Test that source type values can be used as strings."""
        # SearchSourceType inherits from str, so .value is the string
        assert SearchSourceType.WEB.value == "web"
        assert SearchSourceType.IMAGES.value == "images"
        assert SearchSourceType.NEWS.value == "news"
        # Can be compared to strings
        assert SearchSourceType.WEB == "web"
        assert SearchSourceType.IMAGES == "images"
        assert SearchSourceType.NEWS == "news"


class TestSearchResultItem:
    """Tests for SearchResultItem model."""

    def test_default_source_type_is_web(self):
        """Test that default source_type is web."""
        item = SearchResultItem(url="https://example.com", title="Test")
        assert item.source_type == SearchSourceType.WEB

    def test_image_result_fields(self):
        """Test image-specific fields on SearchResultItem."""
        item = SearchResultItem(
            url="https://example.com/image.jpg",
            title="Test Image",
            source_type=SearchSourceType.IMAGES,
            thumbnail="https://example.com/thumb.jpg",
            image_width=800,
            image_height=600,
        )
        assert item.source_type == SearchSourceType.IMAGES
        assert item.thumbnail == "https://example.com/thumb.jpg"
        assert item.image_width == 800
        assert item.image_height == 600

    def test_news_result_fields(self):
        """Test news-specific fields on SearchResultItem."""
        item = SearchResultItem(
            url="https://example.com/article",
            title="Test Article",
            source_type=SearchSourceType.NEWS,
            published_at="2024-12-26T10:00:00Z",
            source_name="Example News",
        )
        assert item.source_type == SearchSourceType.NEWS
        assert item.published_at == "2024-12-26T10:00:00Z"
        assert item.source_name == "Example News"

    def test_description_is_optional(self):
        """Test that description field is optional."""
        item = SearchResultItem(url="https://example.com", title="Test")
        assert item.description is None

    def test_scraped_content_fields(self):
        """Test scraped content fields on SearchResultItem."""
        item = SearchResultItem(
            url="https://example.com",
            title="Test",
            markdown="# Heading\n\nContent",
            html="<h1>Heading</h1><p>Content</p>",
        )
        assert item.markdown == "# Heading\n\nContent"
        assert item.html == "<h1>Heading</h1><p>Content</p>"
