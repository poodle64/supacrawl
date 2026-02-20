"""
Crawl tool for Supacrawl MCP server.

Wraps supacrawl library's CrawlService for MCP consumption.
Note: CrawlService uses streaming (AsyncGenerator), so we collect all results.
"""

from typing import Literal

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.exceptions import SupacrawlValidationError, log_tool_exception, map_exception
from supacrawl.mcp.mcp_common.correlation import generate_correlation_id, get_correlation_id
from supacrawl.mcp.validators import validate_limit, validate_url


async def supacrawl_crawl(
    api_client: SupacrawlServices,
    url: str,
    limit: int = 50,
    max_depth: int = 3,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    formats: list[Literal["markdown", "html", "rawHtml", "links", "screenshot"]] | None = None,
    deduplicate_similar_urls: bool = False,
    allow_external_links: bool = False,
) -> dict:
    """
    Crawl a website starting from URL, discovering and scraping pages.

    This tool combines URL discovery (like map) with content extraction (like scrape),
    automatically following links and extracting content from each page. Use this for
    comprehensive website content extraction.

    **When to use this tool:**
    - You want content from multiple pages on a site
    - You're building a knowledge base from a documentation site
    - You need to archive or analyse an entire section of a website
    - You want to extract content from all pages matching a pattern

    **Common patterns:**
    - For documentation sites: start at /docs/, use include_patterns=[".*\\/docs\\/.*"]
    - For blogs: use include_patterns=[".*\\/blog\\/.*"], exclude_patterns=[".*\\/tag\\/.*"]
    - To avoid duplicates: use deduplicate_similar_urls=True
    - For controlled scope: combine include_patterns with exclude_patterns
    - Start with small limit (10-20) to verify patterns before full crawl

    **Prefer other tools when:**
    - You only need one page → use supacrawl_scrape
    - You want to preview URLs first → use supacrawl_map, then supacrawl_scrape selectively
    - You don't know the site structure → use supacrawl_map first to explore

    Args:
        api_client: Injected SupacrawlServices instance
        url: Starting URL for the crawl
        limit: Maximum number of pages to crawl (default: 50)
        max_depth: Maximum link depth from starting URL (default: 3)
        include_patterns: URL patterns to include (regex patterns).
            Example: [".*\\/blog\\/.*", ".*\\/docs\\/.*"]
        exclude_patterns: URL patterns to exclude (regex patterns).
            Example: [".*\\/login", ".*\\.pdf$", ".*\\/admin\\/.*"]
        formats: Output formats for scraped content (default: ["markdown"])
            - markdown: Clean markdown with resolved URLs
            - html: Cleaned HTML
            - rawHtml: Full unprocessed HTML
            - links: Extracted links
            - screenshot: Page screenshots
        deduplicate_similar_urls: Remove URLs that are similar (different query params,
            fragments, etc. pointing to same content)
        allow_external_links: Follow and crawl links to external domains

    Returns:
        Firecrawl-compatible crawl result:
        {
            "success": true,
            "status": "completed",
            "total": 42,
            "data": [
                {
                    "markdown": "...",
                    "metadata": {
                        "title": "...",
                        "description": "...",
                        "source_url": "..."
                    },
                    "links": [...]
                }
            ]
        }

    Example:
        # Basic crawl
        result = await supacrawl_crawl(url="https://docs.example.com", limit=100)

        # Crawl only blog posts with screenshots
        result = await supacrawl_crawl(
            url="https://example.com/blog",
            include_patterns=[".*\\/blog\\/.*"],
            exclude_patterns=[".*\\/author\\/.*", ".*\\/tag\\/.*"],
            formats=["markdown", "screenshot"],
            limit=50
        )

    Note:
        For very large sites, consider using supacrawl_map first to discover URLs,
        then scrape individual pages as needed.
    """
    # Generate correlation ID for request tracking
    correlation_id = get_correlation_id() or generate_correlation_id()

    try:
        # Validate inputs
        validated_url = validate_url(url)
        assert validated_url is not None  # validate_url raises on None
        validated_limit = validate_limit(limit, "limit", min_value=1, max_value=1000, default=50)
        assert validated_limit is not None  # default=50 ensures non-None

        # Convert Literal list to plain str list for CrawlService
        format_list: list[str] | None = list(formats) if formats else None

        pages = []
        total_crawled = 0

        # CrawlService.crawl() yields CrawlEvent objects
        async for event in api_client.crawl_service.crawl(
            url=validated_url,
            limit=validated_limit,
            max_depth=max_depth,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            formats=format_list,
            deduplicate_similar_urls=deduplicate_similar_urls,
            allow_external_links=allow_external_links,
        ):
            if event.type == "page" and event.data:
                pages.append(event.data.model_dump())
                total_crawled += 1

        return {
            "success": True,
            "status": "completed",
            "total": total_crawled,
            "data": pages,
        }

    except SupacrawlValidationError:
        raise
    except Exception as e:
        log_tool_exception("supacrawl_crawl", e)
        raise map_exception(e, endpoint="/crawl", correlation_id=correlation_id) from e
