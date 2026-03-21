"""Native supacrawl endpoints (health, diagnose, summary)."""

from __future__ import annotations

import logging
import time
from importlib.metadata import version
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from supacrawl.api.auth import get_api_key
from supacrawl.api.dependencies import get_services
from supacrawl.mcp.api_client import SupacrawlServices

logger = logging.getLogger("supacrawl.api.supacrawl")

router = APIRouter(prefix="/supacrawl", tags=["supacrawl"])

# Captured at import time; close enough to app start for uptime tracking.
_START_TIME = time.monotonic()


# --- Request / response models -------------------------------------------


class DiagnoseRequest(BaseModel):
    """Body for POST /supacrawl/diagnose."""

    url: str


class SummaryRequest(BaseModel):
    """Body for POST /supacrawl/summary."""

    url: str
    max_length: int | None = Field(default=None, alias="maxLength")
    focus: str | None = None

    model_config = {"populate_by_name": True}


# --- Endpoints ------------------------------------------------------------


@router.get("/health")
async def health() -> dict[str, Any]:
    """Return service version, uptime, and status. No auth required."""
    uptime_seconds = round(time.monotonic() - _START_TIME)
    return {
        "success": True,
        "version": version("supacrawl"),
        "status": "healthy",
        "uptime_seconds": uptime_seconds,
    }


@router.post("/diagnose")
async def diagnose(
    req: DiagnoseRequest,
    services: SupacrawlServices = Depends(get_services),
    _api_key: str | None = Depends(get_api_key),
) -> dict[str, Any]:
    """Run pre-scrape diagnostics on a URL."""
    from supacrawl.mcp.tools.diagnose import supacrawl_diagnose

    return await supacrawl_diagnose(api_client=services, url=req.url)


@router.post("/summary")
async def summary(
    req: SummaryRequest,
    services: SupacrawlServices = Depends(get_services),
    _api_key: str | None = Depends(get_api_key),
) -> dict[str, Any]:
    """Scrape a URL and return content ready for summarisation."""
    from supacrawl.mcp.tools.summary import supacrawl_summary

    return await supacrawl_summary(
        api_client=services,
        url=req.url,
        max_length=req.max_length,
        focus=req.focus,
    )
