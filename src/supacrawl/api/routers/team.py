"""GET /team/credit-usage stub for n8n Firecrawl credential tests."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from supacrawl.api.auth import get_api_key

router = APIRouter(prefix="/team", tags=["team"])


@router.get("/credit-usage")
async def credit_usage(
    _api_key: str | None = Depends(get_api_key),
) -> dict[str, Any]:
    """Return a static credit-usage response.

    n8n's Firecrawl node tests credentials by hitting this endpoint.
    We always return zero credits (supacrawl is self-hosted).
    """
    return {"success": True, "data": {"credits": 0}}
