"""POST /scrape router; translates v2 protocol to ScrapeService."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from supacrawl.api.auth import get_api_key
from supacrawl.api.dependencies import get_scrape_service
from supacrawl.api.models.scrape import (
    ScrapeDataResponse,
    ScrapeMetadataResponse,
    ScrapeRequest,
    ScrapeResponse,
)
from supacrawl.models import ScrapeResult
from supacrawl.services import ScrapeService

logger = logging.getLogger("supacrawl.api.scrape")

router = APIRouter()

_PROXY_KEYWORDS = frozenset({"basic", "enhanced", "auto"})


def _translate_proxy(value: str | bool | None) -> bool | str | None:
    """Map v2 proxy strings to ScrapeService expectations.

    ``"basic"``, ``"enhanced"``, and ``"auto"`` all map to ``True``.
    A URL string is passed through. Booleans are passed through.
    """
    if isinstance(value, str) and value.lower() in _PROXY_KEYWORDS:
        return True
    return value


def _build_service_kwargs(req: ScrapeRequest) -> dict[str, Any]:
    """Translate a v2 request into keyword arguments for ``ScrapeService.scrape()``."""
    kwargs: dict[str, Any] = {
        "formats": req.formats,
        "only_main_content": req.only_main_content,
        "wait_for": req.wait_for,
        "timeout": req.timeout,
        "include_tags": req.include_tags,
        "exclude_tags": req.exclude_tags,
        "actions": req.actions,
    }

    # maxAge: v2 sends milliseconds; service expects seconds.
    if req.max_age is not None:
        kwargs["max_age"] = req.max_age // 1000

    # storeInCache: false -> bypass cache entirely.
    if req.store_in_cache is False:
        kwargs["max_age"] = 0

    proxy = _translate_proxy(req.proxy)
    if proxy is not None:
        kwargs["proxy"] = proxy  # type: ignore[assignment]

    return kwargs


def _scrape_result_to_response(result: ScrapeResult) -> ScrapeResponse:
    """Map an internal ``ScrapeResult`` to the v2 response shape."""
    if not result.success or result.data is None:
        return ScrapeResponse(success=False, error=result.error)

    data = result.data
    meta = data.metadata

    metadata_resp = ScrapeMetadataResponse(
        title=meta.title,
        description=meta.description,
        source_url=meta.source_url,
        url=meta.source_url,
        status_code=meta.status_code,
        language=meta.language,
    )

    actions_dict: dict[str, Any] | None = None
    if data.actions is not None:
        actions_dict = {
            "screenshots": data.actions.screenshots or [],
            "scrapes": [s.model_dump() for s in (data.actions.scrapes or [])],
        }

    branding_dict: dict[str, Any] | None = None
    if data.branding is not None:
        branding_dict = data.branding.model_dump(exclude_none=True)

    change_tracking_dict: dict[str, Any] | None = None
    if data.change_tracking is not None:
        change_tracking_dict = data.change_tracking.model_dump(exclude_none=True)

    data_resp = ScrapeDataResponse(
        markdown=data.markdown,
        html=data.html,
        raw_html=data.raw_html,
        links=data.links,
        screenshot=data.screenshot,
        metadata=metadata_resp,
        actions=actions_dict,
        branding=branding_dict,
        change_tracking=change_tracking_dict,
    )

    return ScrapeResponse(success=True, data=data_resp)


@router.post("/scrape")
async def scrape(
    req: ScrapeRequest,
    service: ScrapeService = Depends(get_scrape_service),
    _api_key: str | None = Depends(get_api_key),
) -> ScrapeResponse:
    """Scrape a single URL (Firecrawl v2-compatible)."""
    kwargs = _build_service_kwargs(req)
    result = await service.scrape(url=req.url, **kwargs)
    return _scrape_result_to_response(result)
