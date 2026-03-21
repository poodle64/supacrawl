"""Shared fixtures for API tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from supacrawl.api.app import create_app
from supacrawl.api.dependencies import get_map_service, get_scrape_service
from supacrawl.models import (
    MapEvent,
    MapLink,
    MapResult,
    ScrapeData,
    ScrapeMetadata,
    ScrapeResult,
)
from supacrawl.services import MapService, ScrapeService


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


def _make_map_complete_event() -> MapEvent:
    """Build a complete ``MapEvent`` with sample links."""
    return MapEvent(
        type="complete",
        discovered=2,
        result=MapResult(
            success=True,
            links=[
                MapLink(url="https://example.com", title="Example", description="Example page"),
                MapLink(url="https://example.com/about", title="About", description="About page"),
            ],
        ),
    )


async def _mock_map_generator(**kwargs: Any) -> AsyncGenerator[MapEvent, None]:
    """Async generator yielding a single complete event."""
    yield _make_map_complete_event()


@pytest.fixture()
def mock_scrape_service() -> AsyncMock:
    """Return an ``AsyncMock`` standing in for ``ScrapeService``."""
    mock = AsyncMock(spec=ScrapeService)
    mock.scrape.return_value = _make_scrape_result()
    return mock


@pytest.fixture()
def mock_map_service() -> AsyncMock:
    """Return an ``AsyncMock`` standing in for ``MapService``."""
    mock = AsyncMock(spec=MapService)
    mock.map.side_effect = _mock_map_generator
    return mock


@pytest.fixture()
def app(mock_scrape_service: AsyncMock, mock_map_service: AsyncMock) -> FastAPI:
    """Create the FastAPI app with mocked services."""
    application = create_app()
    application.dependency_overrides[get_scrape_service] = lambda: mock_scrape_service
    application.dependency_overrides[get_map_service] = lambda: mock_map_service
    return application


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    """Return a ``TestClient`` wired to the mocked app."""
    return TestClient(app)
