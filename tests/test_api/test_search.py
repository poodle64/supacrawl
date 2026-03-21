"""Tests for POST /search endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


class TestSearchEndpoint:
    """POST /search returns a v2-compatible bucketed response."""

    def test_basic_search(self, client: TestClient) -> None:
        """A minimal request returns success with bucketed data."""
        resp = client.post("/search", json={"query": "example"})
        assert resp.status_code == 200

        body = resp.json()
        assert body["success"] is True
        data = body["data"]

        assert "web" in data
        assert "images" in data
        assert "news" in data

    def test_web_bucket(self, client: TestClient) -> None:
        """Web results contain title, url, description, markdown."""
        resp = client.post("/search", json={"query": "example"})
        web = resp.json()["data"]["web"]

        assert len(web) == 1
        item = web[0]
        assert item["title"] == "Example"
        assert item["url"] == "https://example.com"
        assert item["description"] == "An example page"
        assert item["markdown"] == "# Example"

    def test_images_bucket(self, client: TestClient) -> None:
        """Image results map thumbnail to imageUrl."""
        resp = client.post("/search", json={"query": "example"})
        images = resp.json()["data"]["images"]

        assert len(images) == 1
        item = images[0]
        assert item["title"] == "Photo"
        assert item["url"] == "https://example.com/photo.jpg"
        assert item["imageUrl"] == "https://example.com/thumb.jpg"

    def test_news_bucket(self, client: TestClient) -> None:
        """News results map description to snippet."""
        resp = client.post("/search", json={"query": "example"})
        news = resp.json()["data"]["news"]

        assert len(news) == 1
        item = news[0]
        assert item["title"] == "Breaking News"
        assert item["url"] == "https://news.example.com/article"
        assert item["snippet"] == "Something happened"

    def test_sources_object_translation(self, client: TestClient, mock_search_service: AsyncMock) -> None:
        """V2-style ``[{type: "web"}]`` sources are translated to strings."""
        client.post(
            "/search",
            json={"query": "test", "sources": [{"type": "web"}, {"type": "images"}]},
        )
        call_kwargs = mock_search_service.search.call_args.kwargs
        assert call_kwargs["sources"] == ["web", "images"]

    def test_unknown_sources_dropped(self, client: TestClient, mock_search_service: AsyncMock) -> None:
        """Unknown source types are silently dropped."""
        client.post(
            "/search",
            json={"query": "test", "sources": [{"type": "web"}, {"type": "unknown"}]},
        )
        call_kwargs = mock_search_service.search.call_args.kwargs
        assert call_kwargs["sources"] == ["web"]

    def test_empty_sources_defaults_to_web(self, client: TestClient, mock_search_service: AsyncMock) -> None:
        """If all sources are unknown, defaults to ``["web"]``."""
        client.post(
            "/search",
            json={"query": "test", "sources": [{"type": "bogus"}]},
        )
        call_kwargs = mock_search_service.search.call_args.kwargs
        assert call_kwargs["sources"] == ["web"]

    def test_missing_query_returns_400(self, client: TestClient) -> None:
        """Omitting ``query`` triggers a 400 Bad Request."""
        resp = client.post("/search", json={})
        assert resp.status_code == 400

    def test_service_receives_limit(self, client: TestClient, mock_search_service: AsyncMock) -> None:
        """The limit parameter is forwarded to the service."""
        client.post("/search", json={"query": "test", "limit": 3})
        call_kwargs = mock_search_service.search.call_args.kwargs
        assert call_kwargs["limit"] == 3
