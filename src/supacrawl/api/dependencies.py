"""FastAPI dependency helpers for accessing supacrawl services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from supacrawl.services import ExtractService

if TYPE_CHECKING:
    from supacrawl.mcp.api_client import SupacrawlServices
    from supacrawl.services import ScrapeService


def get_services(request: Request) -> "SupacrawlServices":
    """Return the shared ``SupacrawlServices`` stored on ``app.state``."""
    return request.app.state.services


def get_scrape_service(request: Request) -> "ScrapeService":
    """Return the shared ``ScrapeService``."""
    return get_services(request).scrape_service


def get_extract_service(request: Request) -> ExtractService:
    """Create a per-request ``ExtractService`` backed by the shared scrape service."""
    return ExtractService(scrape_service=get_scrape_service(request))
