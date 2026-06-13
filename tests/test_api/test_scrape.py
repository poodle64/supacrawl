"""Tests for POST /scrape endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from supacrawl.models import ScrapeData, ScrapeMetadata, ScrapeResult


def _make_rich_scrape_result() -> ScrapeResult:
    """Build a ``ScrapeResult`` that includes images, pdf, summary, and llm_extraction."""
    return ScrapeResult(
        success=True,
        data=ScrapeData(
            markdown="# Example",
            html="<h1>Example</h1>",
            raw_html="<html><body><h1>Example</h1></body></html>",
            links=["https://example.com/about"],
            images=["https://example.com/logo.png", "https://example.com/hero.jpg"],
            pdf="JVBERi0xLjQ=",  # minimal base64 placeholder
            summary="A brief summary of the page.",
            llm_extraction={"name": "Example Corp", "founded": 2001},
            metadata=ScrapeMetadata(
                title="Example Domain",
                description="Example page",
                source_url="https://example.com",
                status_code=200,
                language="en",
            ),
        ),
    )


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

    def test_images_in_response(self, client: TestClient, mock_scrape_service: AsyncMock) -> None:
        """images list is present in the response when the service returns it."""
        mock_scrape_service.scrape.return_value = _make_rich_scrape_result()
        resp = client.post("/scrape", json={"url": "https://example.com"})
        data = resp.json()["data"]
        assert data["images"] == [
            "https://example.com/logo.png",
            "https://example.com/hero.jpg",
        ]

    def test_pdf_in_response(self, client: TestClient, mock_scrape_service: AsyncMock) -> None:
        """pdf field is present in the response when the service returns it."""
        mock_scrape_service.scrape.return_value = _make_rich_scrape_result()
        resp = client.post("/scrape", json={"url": "https://example.com"})
        data = resp.json()["data"]
        assert data["pdf"] == "JVBERi0xLjQ="

    def test_summary_in_response(self, client: TestClient, mock_scrape_service: AsyncMock) -> None:
        """summary field is present in the response when the service returns it."""
        mock_scrape_service.scrape.return_value = _make_rich_scrape_result()
        resp = client.post("/scrape", json={"url": "https://example.com"})
        data = resp.json()["data"]
        assert data["summary"] == "A brief summary of the page."

    def test_llm_extraction_serialised_as_json_key(self, client: TestClient, mock_scrape_service: AsyncMock) -> None:
        """llm_extraction is serialised under the wire key 'json'."""
        mock_scrape_service.scrape.return_value = _make_rich_scrape_result()
        resp = client.post("/scrape", json={"url": "https://example.com"})
        data = resp.json()["data"]
        assert data["json"] == {"name": "Example Corp", "founded": 2001}
        assert "llm_extraction" not in data

    def test_absent_fields_are_null(self, client: TestClient) -> None:
        """images, pdf, summary, and json are null when the service omits them."""
        resp = client.post("/scrape", json={"url": "https://example.com"})
        data = resp.json()["data"]
        assert data["images"] is None
        assert data["pdf"] is None
        assert data["summary"] is None
        assert data["json"] is None
