"""Pytest configuration and fixtures for Supacrawl MCP server tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from supacrawl.mcp.api_client import SupacrawlServices


@pytest.fixture
def mock_browser_manager() -> MagicMock:
    """Create mock browser manager."""
    mock = MagicMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.fixture
def mock_scrape_service() -> MagicMock:
    """Create mock scrape service."""
    mock = MagicMock()
    mock.scrape = AsyncMock(
        return_value=MagicMock(
            success=True,
            data=MagicMock(
                markdown="# Test Page\n\nTest content",
                html="<h1>Test Page</h1><p>Test content</p>",
                metadata=MagicMock(title="Test Page", description="Test description"),
            ),
            model_dump=lambda: {
                "success": True,
                "data": {
                    "markdown": "# Test Page\n\nTest content",
                    "html": "<h1>Test Page</h1><p>Test content</p>",
                    "metadata": {"title": "Test Page", "description": "Test description"},
                },
            },
        )
    )
    return mock


@pytest.fixture
def mock_search_service() -> MagicMock:
    """Create mock search service."""
    mock = MagicMock()
    mock.search = AsyncMock(
        return_value=MagicMock(
            success=True,
            data=[
                MagicMock(
                    url="https://example.com",
                    title="Example",
                    description="Example description",
                    source_type="web",
                )
            ],
            model_dump=lambda: {
                "success": True,
                "data": [
                    {
                        "url": "https://example.com",
                        "title": "Example",
                        "description": "Example description",
                        "source_type": "web",
                    }
                ],
            },
        )
    )
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_crawl_service() -> MagicMock:
    """Create mock crawl service."""
    mock = MagicMock()

    async def crawl_generator(*args, **kwargs):
        """Yield mock crawl events."""
        yield MagicMock(
            type="page",
            data=MagicMock(
                markdown="# Page 1",
                metadata={"title": "Page 1"},
                model_dump=lambda: {"markdown": "# Page 1", "metadata": {"title": "Page 1"}},
            ),
        )

    mock.crawl = crawl_generator
    return mock


@pytest.fixture
def mock_map_service() -> MagicMock:
    """Create mock map service."""
    mock = MagicMock()
    mock.map_all = AsyncMock(
        return_value=MagicMock(
            success=True,
            links=["https://example.com/page1", "https://example.com/page2"],
            model_dump=lambda: {
                "success": True,
                "links": ["https://example.com/page1", "https://example.com/page2"],
            },
        )
    )
    return mock


@pytest.fixture
def mock_api_client(
    mock_browser_manager,
    mock_scrape_service,
    mock_search_service,
    mock_crawl_service,
    mock_map_service,
) -> SupacrawlServices:
    """Create mock SupacrawlServices with all services."""
    return SupacrawlServices(
        browser_manager=mock_browser_manager,
        scrape_service=mock_scrape_service,
        crawl_service=mock_crawl_service,
        map_service=mock_map_service,
        search_service=mock_search_service,
    )
