"""
Summary tool for Supacrawl MCP server.

Scrapes web pages and returns content ready for the calling LLM to summarise.
No internal LLM is used - the MCP client (which is an LLM) performs the summarisation.
"""

from typing import Any

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.exceptions import SupacrawlValidationError, log_tool_exception, map_exception
from supacrawl.mcp.mcp_common.correlation import generate_correlation_id, get_correlation_id
from supacrawl.mcp.validators import validate_url


async def supacrawl_summary(
    api_client: SupacrawlServices,
    url: str,
    max_length: int | None = None,
    focus: str | None = None,
) -> dict[str, Any]:
    """
    Generate a summary of a web page.

    This tool scrapes the specified URL and returns content ready for
    the calling LLM to summarise. No internal LLM is used.

    **When to use this tool:**
    - You need a quick overview of a page without reading all content
    - You're triaging multiple pages to find relevant ones
    - You want to understand what a page is about before deeper analysis
    - You're aggregating information from multiple sources

    **Best for:**
    - Quick overviews of long articles
    - Understanding page content before deeper analysis
    - Research and content aggregation
    - Getting the gist of documentation pages

    **Common patterns:**
    - Use focus parameter to target specific aspects ("pricing", "features", "requirements")
    - Use max_length for consistent summary sizes when comparing pages
    - Chain with search: search first, then summarise top results
    - For technical content: use focus="technical details" or focus="API usage"

    **Prefer other tools when:**
    - You need the full content → use supacrawl_scrape
    - You need structured data → use supacrawl_extract
    - You need multiple pages summarised → loop over supacrawl_summary or use supacrawl_crawl

    Args:
        api_client: Injected SupacrawlServices instance
        url: The URL to summarise
        max_length: Optional hint for summary length (e.g., 100 for ~100 words)
        focus: Optional focus area for the summary (e.g., "technical details",
            "pricing information", "key findings")

    Returns:
        Summary-ready result with scraped content:
        {
            "success": true,
            "data": {
                "url": "...",
                "markdown": "...",
                "metadata": {"title": "...", "description": "..."}
            },
            "summary_context": {
                "max_length": 100,
                "focus": "...",
                "instruction": "Summarise the content..."
            }
        }

    Note:
        This tool returns content for the calling LLM to summarise.
        No internal LLM is used - you (the MCP client) perform the summarisation
        using the provided context.
    """
    # Generate correlation ID for request tracking
    correlation_id = get_correlation_id() or generate_correlation_id()

    try:
        # Validate inputs
        validated_url = validate_url(url)
        assert validated_url is not None  # validate_url raises on None

        # Scrape the URL
        scrape_result = await api_client.scrape_service.scrape(
            url=validated_url,
            formats=["markdown"],
            only_main_content=True,
        )

        if not scrape_result.success or not scrape_result.data:
            return {
                "success": False,
                "error": scrape_result.error or "Failed to scrape page",
                "data": None,
                "correlation_id": correlation_id,
            }

        # Build instruction based on parameters
        instruction_parts = ["Summarise the content above."]
        if max_length:
            instruction_parts.append(f"Keep the summary to approximately {max_length} words.")
        if focus:
            instruction_parts.append(f"Focus on: {focus}.")
        instruction_parts.append("Be concise and capture the key points.")

        # Return content ready for the calling LLM to summarise
        return {
            "success": True,
            "data": {
                "url": validated_url,
                "markdown": scrape_result.data.markdown,
                "metadata": {
                    "title": scrape_result.data.metadata.title if scrape_result.data.metadata else None,
                    "description": scrape_result.data.metadata.description if scrape_result.data.metadata else None,
                },
            },
            "summary_context": {
                "max_length": max_length,
                "focus": focus,
                "instruction": " ".join(instruction_parts),
            },
            "correlation_id": correlation_id,
        }

    except SupacrawlValidationError:
        raise
    except Exception as e:
        log_tool_exception("supacrawl_summary", e)
        raise map_exception(e, endpoint="/summary", correlation_id=correlation_id) from e
