"""Shared fixtures for API tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from supacrawl.api.app import create_app
from supacrawl.api.dependencies import get_scrape_service
from supacrawl.models import ScrapeData, ScrapeMetadata, ScrapeResult
from supacrawl.services import ScrapeService


def _make_scrape_result(**overrides: Any) -> ScrapeResult:
    """Build a minimal successful ``ScrapeResult``."""
    defaults: dict[str, Any] = {
        "success": True,
        "data": ScrapeData(
            markdown="# Example",
            html="<h1>Example</h1>",
            raw_html="<html><body><h1>Example</h1></body></html>",
            links=["https://example.com/about"],
            metadata=ScrapeMetadata(
                title="Example Domain",
                description="Example page",
                source_url="https://example.com",
                status_code=200,
                language="en",
            ),
        ),
    }
    defaults.update(overrides)
    return ScrapeResult(**defaults)


@pytest.fixture()
def mock_scrape_service() -> AsyncMock:
    """Return an ``AsyncMock`` standing in for ``ScrapeService``."""
    mock = AsyncMock(spec=ScrapeService)
    mock.scrape.return_value = _make_scrape_result()
    return mock


@pytest.fixture()
def app(mock_scrape_service: AsyncMock) -> FastAPI:
    """Create the FastAPI app with a mocked scrape service."""
    application = create_app()
    application.dependency_overrides[get_scrape_service] = lambda: mock_scrape_service
    return application


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    """Return a ``TestClient`` wired to the mocked app."""
    return TestClient(app)
