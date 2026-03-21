"""Tests for batch scrape endpoints (POST /batch/scrape, GET /batch/scrape/{id})."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from supacrawl.api.app import create_app
from supacrawl.api.dependencies import (
    get_map_service,
    get_scrape_service,
    get_search_service,
)
from supacrawl.api.jobs import JobStore
from supacrawl.models import ScrapeData, ScrapeMetadata, ScrapeResult


def _make_scrape_result(url: str = "https://example.com") -> ScrapeResult:
    """Build a minimal successful ``ScrapeResult`` for the given URL."""
    return ScrapeResult(
        success=True,
        data=ScrapeData(
            markdown="# Example",
            html="<h1>Example</h1>",
            metadata=ScrapeMetadata(
                title="Example",
                source_url=url,
                status_code=200,
            ),
        ),
    )


@pytest.fixture()
def mock_batch_scrape_service() -> AsyncMock:
    """Return an ``AsyncMock`` whose ``.scrape()`` returns per-URL results."""
    mock = AsyncMock()
    mock.scrape.side_effect = lambda url, **kw: _make_scrape_result(url)
    return mock


@pytest.fixture()
def batch_app(
    mock_batch_scrape_service: AsyncMock,
    mock_map_service: AsyncMock,
    mock_search_service: AsyncMock,
) -> FastAPI:
    """Create the FastAPI app with mocked services and a real JobStore."""
    application = create_app()
    application.dependency_overrides[get_scrape_service] = lambda: mock_batch_scrape_service
    application.dependency_overrides[get_map_service] = lambda: mock_map_service
    application.dependency_overrides[get_search_service] = lambda: mock_search_service

    application.state.job_store = JobStore()
    return application


@pytest.fixture()
def batch_client(batch_app: FastAPI) -> TestClient:
    return TestClient(batch_app)


def _wait_for_tasks() -> None:
    """Run the event loop briefly to let background tasks complete."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    loop.run_until_complete(asyncio.sleep(0.1))


class TestBatchScrapeCreate:
    """POST /batch/scrape creates a job and returns its ID."""

    def test_returns_job_id(self, batch_client: TestClient) -> None:
        resp = batch_client.post(
            "/batch/scrape",
            json={"urls": ["https://a.com", "https://b.com"]},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["success"] is True
        assert "id" in body
        assert isinstance(body["id"], str)

    def test_missing_urls_returns_400(self, batch_client: TestClient) -> None:
        resp = batch_client.post("/batch/scrape", json={})
        assert resp.status_code == 400

    def test_unknown_fields_ignored(self, batch_client: TestClient) -> None:
        resp = batch_client.post(
            "/batch/scrape",
            json={
                "urls": ["https://a.com"],
                "webhook": "https://hook.example.com",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestBatchScrapeStatus:
    """GET /batch/scrape/{id} returns job status with paginated data."""

    def test_job_not_found(self, batch_client: TestClient) -> None:
        resp = batch_client.get("/batch/scrape/nonexistent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "not found" in body["error"]

    def test_lifecycle_post_then_get(self, batch_client: TestClient) -> None:
        """POST creates job, background task runs, GET returns completed data."""
        post_resp = batch_client.post(
            "/batch/scrape",
            json={"urls": ["https://a.com", "https://b.com"]},
        )
        job_id = post_resp.json()["id"]

        _wait_for_tasks()

        get_resp = batch_client.get(f"/batch/scrape/{job_id}")
        assert get_resp.status_code == 200

        body = get_resp.json()
        assert body["status"] == "completed"
        assert body["total"] == 2
        assert body["completed"] == 2
        assert len(body["data"]) == 2

        # Verify data shape matches v2 scrape output
        page = body["data"][0]
        assert "markdown" in page
        assert "metadata" in page

    def test_scrape_options_forwarded(
        self,
        batch_client: TestClient,
        mock_batch_scrape_service: AsyncMock,
    ) -> None:
        """Flat scrape options are forwarded to the scrape service."""
        post_resp = batch_client.post(
            "/batch/scrape",
            json={
                "urls": ["https://a.com"],
                "formats": ["markdown"],
                "onlyMainContent": False,
                "timeout": 60000,
            },
        )
        assert post_resp.json()["id"]

        _wait_for_tasks()

        # Verify the scrape service was called with translated kwargs
        call_kwargs = mock_batch_scrape_service.scrape.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("only_main_content") is False
        assert call_kwargs.kwargs.get("timeout") == 60000
        assert call_kwargs.kwargs.get("formats") == ["markdown"]


class TestBatchScrapeErrorHandling:
    """Individual URL failures are recorded but do not stop the batch."""

    def test_partial_failure(
        self,
        batch_client: TestClient,
        mock_batch_scrape_service: AsyncMock,
    ) -> None:
        """One URL fails; the other succeeds. Job still completes."""
        call_count = 0

        async def _side_effect(url: str, **kwargs: object) -> ScrapeResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Network error")
            return _make_scrape_result(url)

        mock_batch_scrape_service.scrape.side_effect = _side_effect

        post_resp = batch_client.post(
            "/batch/scrape",
            json={"urls": ["https://fail.com", "https://ok.com"]},
        )
        job_id = post_resp.json()["id"]

        _wait_for_tasks()

        get_resp = batch_client.get(f"/batch/scrape/{job_id}")
        body = get_resp.json()

        assert body["status"] == "completed"
        assert body["completed"] == 2
        assert len(body["data"]) == 2

        # First entry should be an error record
        assert "error" in body["data"][0]
        # Second entry should be normal scrape data
        assert "markdown" in body["data"][1]
