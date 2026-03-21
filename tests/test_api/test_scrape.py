"""Tests for POST /scrape endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


class TestScrapeEndpoint:
    """POST /scrape returns a v2-compatible camelCase response."""

    def test_basic_scrape(self, client: TestClient) -> None:
        """A minimal request returns success with correct shape."""
        resp = client.post("/scrape", json={"url": "https://example.com"})
        assert resp.status_code == 200

        body = resp.json()
        assert body["success"] is True
        data = body["data"]

        assert data["markdown"] == "# Example"
        assert data["html"] == "<h1>Example</h1>"
        assert data["rawHtml"] == "<html><body><h1>Example</h1></body></html>"
        assert data["links"] == ["https://example.com/about"]

    def test_metadata_camel_case(self, client: TestClient) -> None:
        """Metadata fields are serialised in camelCase with v2 aliases."""
        resp = client.post("/scrape", json={"url": "https://example.com"})
        meta = resp.json()["data"]["metadata"]

        assert meta["title"] == "Example Domain"
        assert meta["description"] == "Example page"
        assert meta["sourceURL"] == "https://example.com"
        assert meta["url"] == "https://example.com"
        assert meta["statusCode"] == 200
        assert meta["language"] == "en"

    def test_service_called_with_url(self, client: TestClient, mock_scrape_service: AsyncMock) -> None:
        """The service receives the requested URL."""
        client.post("/scrape", json={"url": "https://example.com"})
        mock_scrape_service.scrape.assert_awaited_once()
        call_kwargs = mock_scrape_service.scrape.call_args
        assert call_kwargs.kwargs["url"] == "https://example.com"

    def test_formats_passed_through(self, client: TestClient, mock_scrape_service: AsyncMock) -> None:
        """Requested formats are forwarded to the service."""
        client.post(
            "/scrape",
            json={"url": "https://example.com", "formats": ["markdown", "html"]},
        )
        call_kwargs = mock_scrape_service.scrape.call_args.kwargs
        assert call_kwargs["formats"] == ["markdown", "html"]

    def test_missing_url_returns_400(self, client: TestClient) -> None:
        """Omitting ``url`` triggers a 400 Bad Request."""
        resp = client.post("/scrape", json={})
        assert resp.status_code == 400

    def test_error_response_shape(self, client: TestClient) -> None:
        """Validation errors return the standard error envelope."""
        resp = client.post("/scrape", json={})
        body = resp.json()
        assert body["success"] is False
        assert "error" in body
