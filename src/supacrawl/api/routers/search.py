"""POST /search router; translates v2 protocol to SearchService."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from supacrawl.api.auth import get_api_key
from supacrawl.api.dependencies import get_search_service
from supacrawl.api.models.search import (
    ImageResultItem,
    NewsResultItem,
    SearchDataResponse,
    SearchRequest,
    SearchResponse,
    WebResultItem,
)
from supacrawl.models import SearchResult, SearchSourceType
from supacrawl.services.search.service import SearchService

logger = logging.getLogger("supacrawl.api.search")

router = APIRouter()


def _search_result_to_response(result: SearchResult) -> SearchResponse:
    """Map an internal ``SearchResult`` to the v2 bucketed response shape."""
    if not result.success:
        return SearchResponse(success=False, error=result.error)

    web: list[WebResultItem] = []
    images: list[ImageResultItem] = []
    news: list[NewsResultItem] = []

    for item in result.data:
        if item.source_type == SearchSourceType.WEB:
            web.append(
                WebResultItem(
                    title=item.title,
                    url=item.url,
                    description=item.description,
                    markdown=item.markdown,
                )
            )
        elif item.source_type == SearchSourceType.IMAGES:
            images.append(
                ImageResultItem(
                    title=item.title,
                    url=item.url,
                    image_url=item.thumbnail,
                )
            )
        elif item.source_type == SearchSourceType.NEWS:
            news.append(
                NewsResultItem(
                    title=item.title,
                    url=item.url,
                    snippet=item.description,
                )
            )

    data = SearchDataResponse(web=web, images=images, news=news)
    return SearchResponse(success=True, data=data)


@router.post("/search")
async def search(
    req: SearchRequest,
    service: SearchService = Depends(get_search_service),
    _api_key: str | None = Depends(get_api_key),
) -> SearchResponse:
    """Search the web (Firecrawl v2-compatible)."""
    result = await service.search(
        query=req.query,
        limit=req.limit,
        sources=req.sources,  # type: ignore[arg-type]
    )
    return _search_result_to_response(result)
