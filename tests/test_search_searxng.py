"""Unit tests for SearXNGProvider (#156).

SearXNGProvider had zero test coverage before this: the multi-word-query
regression that prompted #156 could not have been caught by CI. These tests
exercise request building (query, params, domain/time filters) and response
mapping via a fake httpx client, mirroring the style used for the other
providers in test_search_providers.py / test_search_provider_filters.py.
"""

import os
from typing import Any
from unittest.mock import patch

import pytest

from supacrawl.models import SearchFilters, SearchSourceType
from supacrawl.services.search.searxng import SearXNGProvider

CORRELATION_ID = "test-1234"


class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._data


class _FakeClient:
    """Captures the last outgoing request and returns a canned JSON body."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.last: dict[str, Any] = {}

    async def get(self, url: str, *, params: Any = None) -> _FakeResponse:
        self.last = {"url": url, "params": params}
        return _FakeResponse(self._data)

    async def aclose(self) -> None:
        pass


WEB_RESPONSE = {
    "results": [
        {"url": "https://example.com/1", "title": "Result One", "content": "First snippet."},
        {"url": "https://example.com/2", "title": "Result Two", "content": "Second snippet."},
    ]
}

IMAGE_RESPONSE = {
    "results": [
        {
            "url": "https://example.com/photo.jpg",
            "img_src": "https://example.com/photo-full.jpg",
            "title": "A Photo",
            "thumbnail_src": "https://example.com/thumb.jpg",
            "img_format": {"width": 800, "height": 600},
        }
    ]
}

NEWS_RESPONSE = {
    "results": [
        {
            "url": "https://news.example.com/story",
            "title": "Breaking Story",
            "content": "Story snippet.",
            "publishedDate": "2026-06-13",
            "engine": "bing news",
        }
    ]
}


class TestSearXNGProvider:
    """Request-building and response-mapping tests for SearXNGProvider."""

    @pytest.mark.asyncio
    async def test_search_web_field_mapping(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient(WEB_RESPONSE)
            provider._http_client = fake  # type: ignore[assignment]

            results = await provider.search_web("prometheus alertmanager grouping", 5, CORRELATION_ID)

            assert len(results) == 2
            assert results[0].url == "https://example.com/1"
            assert results[0].title == "Result One"
            assert results[0].description == "First snippet."
            assert results[0].source_type == SearchSourceType.WEB
            assert fake.last["params"]["q"] == "prometheus alertmanager grouping"
            assert fake.last["params"]["categories"] == "general"
            assert fake.last["params"]["format"] == "json"
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_search_web_respects_limit(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient(WEB_RESPONSE)
            provider._http_client = fake  # type: ignore[assignment]

            results = await provider.search_web("query", 1, CORRELATION_ID)

            assert len(results) == 1
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_search_web_missing_optional_fields(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient({"results": [{"url": "https://x.com"}]})
            provider._http_client = fake  # type: ignore[assignment]

            results = await provider.search_web("q", 5, CORRELATION_ID)

            assert len(results) == 1
            assert results[0].title == ""
            assert results[0].description == ""
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_search_web_empty_results(self) -> None:
        """Regression guard for #156: an empty upstream result set must map to []."""
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient({"results": []})
            provider._http_client = fake  # type: ignore[assignment]

            results = await provider.search_web("prometheus alertmanager grouping", 5, CORRELATION_ID)

            assert results == []
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_search_images_field_mapping(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient(IMAGE_RESPONSE)
            provider._http_client = fake  # type: ignore[assignment]

            results = await provider.search_images("photo", 5, CORRELATION_ID)

            assert len(results) == 1
            item = results[0]
            assert item.url == "https://example.com/photo.jpg"
            assert item.source_type == SearchSourceType.IMAGES
            assert item.thumbnail == "https://example.com/thumb.jpg"
            assert item.image_width == 800
            assert item.image_height == 600
            assert fake.last["params"]["categories"] == "images"
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_search_images_falls_back_to_img_src(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            body = {"results": [{"img_src": "https://example.com/only-img.jpg", "title": "X"}]}
            fake = _FakeClient(body)
            provider._http_client = fake  # type: ignore[assignment]

            results = await provider.search_images("q", 5, CORRELATION_ID)

            assert results[0].url == "https://example.com/only-img.jpg"
            assert results[0].thumbnail == "https://example.com/only-img.jpg"
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_search_news_field_mapping(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient(NEWS_RESPONSE)
            provider._http_client = fake  # type: ignore[assignment]

            results = await provider.search_news("news query", 5, CORRELATION_ID)

            assert len(results) == 1
            item = results[0]
            assert item.url == "https://news.example.com/story"
            assert item.source_type == SearchSourceType.NEWS
            assert item.published_at == "2026-06-13"
            assert item.source_name == "bing news"
            assert fake.last["params"]["categories"] == "news"
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_domain_filters_rewrite_query(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient({"results": []})
            provider._http_client = fake  # type: ignore[assignment]

            await provider.search_web(
                "ai",
                5,
                CORRELATION_ID,
                SearchFilters(include_domains=["a.com"], exclude_domains=["b.com"]),
            )

            assert fake.last["params"]["q"] == "ai site:a.com -site:b.com"
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_supported_time_range_is_forwarded(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient({"results": []})
            provider._http_client = fake  # type: ignore[assignment]

            await provider.search_web("ai", 5, CORRELATION_ID, SearchFilters(time_range="month"))

            assert fake.last["params"]["time_range"] == "month"
        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_unsupported_time_range_is_dropped(self) -> None:
        """SearXNG has no 'week' bucket; the filter must not be forwarded verbatim."""
        provider = SearXNGProvider(url="http://searxng.invalid")
        try:
            fake = _FakeClient({"results": []})
            provider._http_client = fake  # type: ignore[assignment]

            await provider.search_web("ai", 5, CORRELATION_ID, SearchFilters(time_range="week"))

            assert "time_range" not in fake.last["params"]
        finally:
            await provider.close()

    def test_is_available_false_without_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            provider = SearXNGProvider(url=None)
        assert not provider.is_available()

    def test_is_available_true_with_url(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid")
        assert provider.is_available()

    def test_reads_url_from_env(self) -> None:
        with patch.dict(os.environ, {"SEARXNG_URL": "http://env-searxng.invalid"}):
            provider = SearXNGProvider()
        assert provider.is_available()

    def test_url_is_stripped_of_trailing_slash(self) -> None:
        provider = SearXNGProvider(url="http://searxng.invalid/")
        assert provider._url == "http://searxng.invalid"
