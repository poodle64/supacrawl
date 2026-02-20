"""
Extract tool for Supacrawl MCP server.

Scrapes web pages and returns content ready for the calling LLM to extract
structured data. No internal LLM is used - the MCP client (which is an LLM)
performs the extraction.
"""

from typing import Any

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.config import logger
from supacrawl.mcp.exceptions import SupacrawlValidationError, log_tool_exception, map_exception
from supacrawl.mcp.mcp_common.correlation import generate_correlation_id, get_correlation_id
from supacrawl.mcp.validators import validate_prompt, validate_urls


async def supacrawl_extract(
    api_client: SupacrawlServices,
    urls: list[str] | str,
    prompt: str | None = None,
    schema: dict[str, Any] | str | None = None,
    allow_external_links: bool = False,
) -> dict[str, Any]:
    """
    Extract structured information from web pages using LLM.

    This tool scrapes the specified URLs and uses an LLM to extract
    structured data according to your prompt and/or schema.

    **When to use this tool:**
    - You need structured data (JSON) from web pages
    - You want to extract specific fields from multiple URLs at once
    - You have a schema defining what data you need
    - You're building datasets from web content

    **Best for extracting:**
    - Product information (name, price, description, availability)
    - Contact details (emails, phone numbers, addresses)
    - Article metadata (author, date, categories, tags)
    - Event information (dates, venues, speakers)
    - Any custom data matching your schema

    **Common patterns:**
    - Provide both prompt AND schema for best results
    - Keep schemas simple and flat when possible
    - Use descriptive field names in schema (LLM uses them as hints)
    - For e-commerce: extract from product listing pages, not search results
    - Batch related URLs together (same site/structure) for consistency

    **Prefer other tools when:**
    - You just need the page content → use supacrawl_scrape with formats=["markdown"]
    - You need a summary, not structured data → use supacrawl_summary
    - You want to scrape with your own processing → use supacrawl_scrape

    Args:
        api_client: Injected SupacrawlServices instance
        urls: URLs to extract data from (1-10 URLs)
        prompt: Natural language description of what to extract.
            Example: "Extract the product name, price, and availability"
        schema: JSON schema defining the structure of extracted data.
            Example: {"type": "object", "properties": {"name": {"type": "string"}}}
        allow_external_links: Whether to follow and extract from external links

    Returns:
        Extraction-ready result with scraped content:
        {
            "success": true,
            "data": [
                {
                    "url": "...",
                    "success": true,
                    "markdown": "...",
                    "metadata": {"title": "...", "description": "..."}
                }
            ],
            "extraction_context": {
                "prompt": "...",
                "schema": {...},
                "instruction": "Extract structured data..."
            }
        }

    Note:
        This tool returns content for the calling LLM to extract.
        No internal LLM is used - you (the MCP client) perform the extraction
        using the provided schema and prompt.
    """
    # Generate correlation ID for request tracking
    correlation_id = get_correlation_id() or generate_correlation_id()

    try:
        # Validate inputs
        validated_urls = validate_urls(urls, "urls", min_count=1, max_count=10)
        validated_prompt = validate_prompt(prompt, "prompt", allow_none=True)

        # Scrape all URLs and collect content
        results = []
        for url in validated_urls:
            try:
                scrape_result = await api_client.scrape_service.scrape(
                    url=url,
                    formats=["markdown"],
                    only_main_content=True,
                )

                if scrape_result.success and scrape_result.data:
                    results.append(
                        {
                            "url": url,
                            "success": True,
                            "markdown": scrape_result.data.markdown,
                            "metadata": {
                                "title": scrape_result.data.metadata.title if scrape_result.data.metadata else None,
                                "description": scrape_result.data.metadata.description
                                if scrape_result.data.metadata
                                else None,
                            },
                        }
                    )
                else:
                    results.append(
                        {
                            "url": url,
                            "success": False,
                            "error": scrape_result.error or "Failed to scrape page",
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to scrape {url}: {e}")
                results.append(
                    {
                        "url": url,
                        "success": False,
                        "error": str(e),
                    }
                )

        # Return content ready for the calling LLM to extract
        return {
            "success": all(r.get("success", False) for r in results),
            "data": results,
            "extraction_context": {
                "prompt": validated_prompt,
                "schema": schema,
                "instruction": (
                    "Extract structured data from the markdown content above. "
                    "Use the provided schema to structure your response. "
                    "Return valid JSON matching the schema."
                ),
            },
            "correlation_id": correlation_id,
        }

    except SupacrawlValidationError:
        raise
    except Exception as e:
        log_tool_exception("supacrawl_extract", e)
        raise map_exception(e, endpoint="/extract", correlation_id=correlation_id) from e
