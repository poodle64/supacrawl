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


class TestSearchHonestySignals:
    """The REST surface must not hide what the MCP surface shows (#166).

    A REST caller hitting a CAPTCHA-walled or otherwise failing backend used to
    get `success: true` with empty buckets and no way to tell "no matches" from
    "the backend has stopped answering" — the silent-failure class #158/#161
    closed for MCP callers only.
    """

    def test_default_response_carries_the_signal_fields(self, client: TestClient) -> None:
        body = client.post("/search", json={"query": "example"}).json()

        assert "provider" in body
        assert body["providerFallback"] is False
        assert body["unresponsiveEngines"] == []
        assert body["allRecentEmpty"] is False

    def test_provider_and_fallback_are_reported(self, client: TestClient, mock_search_service: AsyncMock) -> None:
        from supacrawl.models import SearchResult

        mock_search_service.search.return_value = SearchResult(
            success=True, data=[], provider="duckduckgo", provider_fallback=True
        )

        body = client.post("/search", json={"query": "example"}).json()

        assert body["provider"] == "duckduckgo"
        assert body["providerFallback"] is True

    def test_empty_result_from_a_dead_backend_is_distinguishable(
        self, client: TestClient, mock_search_service: AsyncMock
    ) -> None:
        """The whole point: `data` is empty either way, so the signals must differ."""
        from supacrawl.models import SearchEngineError, SearchResult

        mock_search_service.search.return_value = SearchResult(
            success=True,
            data=[],
            provider="searxng",
            unresponsive_engines=[SearchEngineError(engine="google", reason="CAPTCHA")],
            all_recent_empty=True,
        )

        body = client.post("/search", json={"query": "example"}).json()

        assert body["success"] is True
        assert body["data"]["web"] == []
        assert body["allRecentEmpty"] is True
        assert body["unresponsiveEngines"] == [{"engine": "google", "reason": "CAPTCHA"}]

    def test_failed_search_still_carries_the_signals(self, client: TestClient, mock_search_service: AsyncMock) -> None:
        """The failure path is where provenance matters most, not least."""
        from supacrawl.models import SearchEngineError, SearchResult

        mock_search_service.search.return_value = SearchResult(
            success=False,
            data=[],
            error="all providers failed",
            provider="searxng",
            provider_fallback=True,
            unresponsive_engines=[SearchEngineError(engine="bing", reason="timeout")],
            all_recent_empty=True,
        )

        body = client.post("/search", json={"query": "example"}).json()

        assert body["success"] is False
        assert body["error"] == "all providers failed"
        assert body["provider"] == "searxng"
        assert body["providerFallback"] is True
        assert body["allRecentEmpty"] is True
        assert body["unresponsiveEngines"] == [{"engine": "bing", "reason": "timeout"}]

    def test_rest_carries_every_signal_the_mcp_surface_does(self) -> None:
        """Parity, checked structurally so a new signal cannot land on one surface only.

        The MCP tool returns `result.model_dump()`, so it gains any field added
        to `SearchResult` for free. This asserts the REST envelope keeps up.
        """
        from supacrawl.api.models.search import SearchResponse
        from supacrawl.models import SearchResult

        signals = set(SearchResult.model_fields) - {"success", "data", "error"}

        assert signals <= set(SearchResponse.model_fields)

    def test_v2_compatible_fields_are_unchanged(self, client: TestClient) -> None:
        """Additive only: a Firecrawl v2 client sees exactly what it saw before."""
        body = client.post("/search", json={"query": "example"}).json()

        assert body["success"] is True
        assert set(body["data"]) == {"web", "images", "news"}
        assert body["data"]["web"][0]["url"] == "https://example.com"
