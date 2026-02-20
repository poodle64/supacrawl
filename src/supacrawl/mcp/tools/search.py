"""
Search tool for Supacrawl MCP server.

Provides web search functionality with optional result scraping.
"""

import asyncio
from typing import Any, Literal

import httpx

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.config import logger
from supacrawl.mcp.exceptions import SupacrawlValidationError, log_tool_exception, map_exception
from supacrawl.mcp.mcp_common.correlation import generate_correlation_id, get_correlation_id
from supacrawl.mcp.validators import (
    enhance_query_with_current_year,
    validate_formats,
    validate_limit,
    validate_query,
    validate_sources,
)


async def _fetch_url_metadata(url: str, timeout: float = 5.0) -> dict[str, Any]:
    """
    Fetch lightweight metadata for a URL using HEAD request.

    Falls back to GET with stream if HEAD is not allowed.

    Args:
        url: URL to fetch metadata for
        timeout: Request timeout in seconds

    Returns:
        Dictionary with metadata fields (content_type, content_length, last_modified)
    """
    metadata: dict[str, Any] = {}

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Supacrawl/1.0)"},
    ) as client:
        try:
            # Try HEAD request first (lightweight)
            response = await client.head(url)

            # Some servers don't support HEAD, fall back to GET with stream
            if response.status_code == 405:
                async with client.stream("GET", url) as response:
                    headers = response.headers
            else:
                headers = response.headers

            # Extract useful headers
            if "content-type" in headers:
                metadata["content_type"] = headers["content-type"].split(";")[0].strip()

            if "content-length" in headers:
                try:
                    metadata["content_length"] = int(headers["content-length"])
                except ValueError:
                    pass

            if "last-modified" in headers:
                metadata["last_modified"] = headers["last-modified"]

        except httpx.TimeoutException:
            metadata["error"] = "timeout"
        except httpx.RequestError as e:
            metadata["error"] = str(e)
        except Exception as e:
            logger.debug(f"Failed to fetch metadata for {url}: {e}")
            metadata["error"] = "fetch_failed"

    return metadata


async def _enrich_results_with_metadata(
    results: list[dict[str, Any]],
    timeout: float = 5.0,
) -> list[dict[str, Any]]:
    """
    Enrich search results with lightweight metadata from HEAD requests.

    Only processes web results (not images/news).

    Args:
        results: List of search result dictionaries
        timeout: Per-request timeout in seconds

    Returns:
        Results with metadata field added
    """
    # Filter to web results only (images/news don't need metadata fetch)
    web_results = [(i, r) for i, r in enumerate(results) if r.get("source_type") == "web"]

    if not web_results:
        return results

    # Fetch metadata in parallel
    tasks = [_fetch_url_metadata(r["url"], timeout) for _, r in web_results]
    metadata_list = await asyncio.gather(*tasks)

    # Merge metadata into results
    for (idx, _), metadata in zip(web_results, metadata_list, strict=True):
        if metadata and not metadata.get("error"):
            results[idx]["metadata"] = metadata

    return results


async def supacrawl_search(
    api_client: SupacrawlServices,
    query: str,
    limit: int = 5,
    sources: list[Literal["web", "images", "news"]] | None = None,
    scrape_results: bool = False,
    formats: list[Literal["markdown", "html"]] | None = None,
    only_main_content: bool = True,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """
    Search the web and optionally scrape result pages.

    This is the most powerful web search tool available for finding information
    across the web. Use it when you need to find specific information and
    don't know which website contains it.

    Supports multiple source types (web, images, news) and can optionally
    scrape the content from web result pages.

    **When to use this tool:**
    - You need to find information but don't know which website has it
    - You want to discover URLs related to a topic
    - You need recent news articles on a subject
    - You're looking for images matching a description

    **Common patterns:**
    - For current/recent info: the query is automatically enhanced with current year
    - For specific sites: use "site:example.com" in query
    - For exact phrases: wrap in quotes ("exact phrase")
    - To exclude terms: use minus (-unwanted)
    - For deep content: set scrape_results=True to get full page content
    - For research: search first (scrape_results=False), then scrape relevant URLs
    - To preview before scraping: use include_metadata=True to get content type/size

    **Prefer other tools when:**
    - You already have the URL → use supacrawl_scrape
    - You want all pages from a known site → use supacrawl_map or supacrawl_crawl
    - You need structured data extraction → use supacrawl_extract

    Args:
        api_client: Injected SupacrawlServices instance
        query: Search query string. Supports search operators:
            - "quotes" for exact match
            - -word to exclude
            - site:example.com to limit to domain
            - intitle:word for title matches
            - inurl:word for URL matches
        limit: Maximum number of results per source type (1-10, default 5)
        sources: Source types to search. Defaults to ["web"].
            - "web": Standard web pages
            - "images": Image search results
            - "news": News articles
        scrape_results: Whether to scrape content from web result pages
        formats: Output formats when scraping (markdown, html)
        only_main_content: Extract only main content when scraping
        include_metadata: Fetch lightweight metadata (content_type, content_length,
            last_modified) for web results via HEAD requests. Useful for deciding
            which results to scrape without loading full pages.

    Returns:
        Firecrawl-compatible search result:
        {
            "success": true,
            "data": [
                {
                    "url": "https://...",
                    "title": "...",
                    "description": "...",
                    "source_type": "web",  // or "images", "news"
                    "markdown": "...",  // If scrape_results=true (web only)
                    "html": "...",  // If scrape_results=true
                    "metadata": {  // If include_metadata=true (web only)
                        "content_type": "text/html",
                        "content_length": 45000,
                        "last_modified": "Sat, 01 Jan 2025 00:00:00 GMT"
                    },
                    // Image-specific:
                    "thumbnail": "...",
                    "image_width": 1920,
                    "image_height": 1080,
                    // News-specific:
                    "published_at": "2024-01-15T...",
                    "source_name": "..."
                }
            ]
        }

    Example:
        # Basic web search
        result = await supacrawl_search(query="python web scraping 2024", limit=5)

        # Image search
        result = await supacrawl_search(
            query="python logo",
            sources=["images"],
            limit=10
        )

        # News search with content scraping
        result = await supacrawl_search(
            query="AI breakthroughs",
            sources=["news", "web"],
            scrape_results=True,
            formats=["markdown"]
        )

        # Search with metadata to preview before scraping
        result = await supacrawl_search(
            query="python documentation",
            include_metadata=True
        )

    Note:
        - DuckDuckGo (default) is free but may have rate limits
        - Brave Search requires BRAVE_API_KEY
        - Scraping is only applied to "web" source type results
        - Metadata fetch uses lightweight HEAD requests (fast, no page content)
    """
    # Generate correlation ID for request tracking
    correlation_id = get_correlation_id() or generate_correlation_id()

    try:
        # Validate inputs - provides helpful error messages
        validated_query = validate_query(query)
        # Enhance query with current year if time-sensitive (LLMs often use training cutoff year)
        validated_query = enhance_query_with_current_year(validated_query)
        validated_limit = validate_limit(limit, "limit", min_value=1, max_value=10, default=5)
        assert validated_limit is not None  # default=5 ensures non-None
        validated_sources = validate_sources(sources)
        validated_formats = validate_formats(formats, allowed_formats=["markdown", "html"])

        # Default to web search
        if validated_sources is None:
            validated_sources = ["web"]

        from supacrawl.services.search import ScrapeOptions, SourceType

        typed_sources: list[SourceType] = validated_sources  # type: ignore[assignment]

        scrape_options = None
        if scrape_results:
            typed_formats: list[Literal["markdown", "html"]] = validated_formats or ["markdown"]  # type: ignore[assignment]
            scrape_options = ScrapeOptions(
                formats=typed_formats,
                only_main_content=only_main_content,
            )

        result = await api_client.search_service.search(
            query=validated_query,
            limit=validated_limit,
            sources=typed_sources,
            scrape_options=scrape_options,
        )

        response = result.model_dump()

        # Enrich web results with lightweight metadata if requested
        if include_metadata and not scrape_results:
            # Only fetch metadata if we're not already scraping (scraping includes richer metadata)
            response["data"] = await _enrich_results_with_metadata(response.get("data", []))

        # Include the actual query used (may differ from input if year was corrected)
        if validated_query != query:
            response["query_used"] = validated_query
            response["query_original"] = query

        return response

    except SupacrawlValidationError:
        raise
    except Exception as e:
        log_tool_exception("supacrawl_search", e)
        raise map_exception(e, endpoint="/search", correlation_id=correlation_id) from e
