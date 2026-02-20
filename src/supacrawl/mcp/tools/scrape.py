"""
Scrape tool for Supacrawl MCP server.

Wraps supacrawl library's ScrapeService for MCP consumption.
"""

from typing import Any, Literal

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.exceptions import SupacrawlValidationError, log_tool_exception, map_exception
from supacrawl.mcp.mcp_common.correlation import generate_correlation_id, get_correlation_id
from supacrawl.mcp.validators import validate_timeout, validate_url


async def supacrawl_scrape(
    api_client: SupacrawlServices,
    url: str,
    formats: list[
        Literal[
            "markdown",
            "html",
            "rawHtml",
            "links",
            "screenshot",
            "pdf",
            "json",
            "images",
            "branding",
            "summary",
        ]
    ]
    | None = None,
    only_main_content: bool = True,
    wait_for: int = 0,
    timeout: int = 30000,
    screenshot_full_page: bool = True,
    actions: list[dict[str, Any]] | None = None,
    json_schema: dict[str, Any] | None = None,
    json_prompt: str | None = None,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    max_age: int = 0,
) -> dict:
    """
    Scrape a single URL and return content in specified formats.

    This is the primary tool for extracting content from web pages. It supports
    multiple output formats, page interactions, and LLM-powered extraction.

    **When to use this tool:**
    - You have a specific URL and need its content
    - You want clean markdown for reading/analysis
    - You need screenshots or PDFs of a page
    - You need to extract structured data (json format) from a single page

    **Common patterns:**
    - For JS-heavy sites (SPAs, React, Vue): set wait_for=3000 or higher
    - For clean article text: use only_main_content=True (default)
    - For full page including nav/footer: use only_main_content=False
    - If content is minimal/empty, try increasing wait_for (page may need time to load)
    - For login-protected content: use actions to click buttons/fill forms first
    - For infinite scroll pages: use actions with scroll + wait sequences

    **Prefer other tools when:**
    - You don't know the URL → use supacrawl_search first
    - You need to find pages on a site → use supacrawl_map
    - You need content from multiple pages → use supacrawl_crawl
    - You want a quick summary → use supacrawl_summary

    Args:
        api_client: Injected SupacrawlServices instance
        url: The URL to scrape
        formats: Output formats to return. Options:
            - markdown: Clean markdown with resolved URLs (default)
            - html: Cleaned HTML with boilerplate removed
            - rawHtml: Full unprocessed HTML
            - links: All extracted links
            - images: All image URLs
            - screenshot: Base64-encoded PNG
            - pdf: Base64-encoded PDF document
            - json: LLM-extracted structured data (requires json_schema or json_prompt)
            - branding: Brand identity (colours, fonts, logo)
            - summary: LLM-generated 2-3 sentence summary
        only_main_content: Extract only main content, excluding headers/footers/sidebars
        wait_for: Additional wait time in ms after page load (for dynamic content)
        timeout: Page load timeout in ms (default: 30000)
        screenshot_full_page: Capture full scrollable page vs viewport only
        actions: Page actions to execute before capturing content. Each action is a dict:
            - {"type": "wait", "milliseconds": 1000} - Wait for time
            - {"type": "wait", "selector": "#content"} - Wait for element
            - {"type": "click", "selector": "button.submit"} - Click element
            - {"type": "type", "selector": "input", "text": "hello"} - Type text
            - {"type": "scroll", "direction": "down"} - Scroll page
            - {"type": "screenshot"} - Capture mid-workflow screenshot
            - {"type": "press", "key": "Enter"} - Press keyboard key
            - {"type": "executeJavascript", "script": "..."} - Run custom JS
        json_schema: JSON schema for structured extraction (for json format).
            Example: {"type": "object", "properties": {"title": {"type": "string"}}}
        json_prompt: Custom prompt for LLM extraction (for json format).
            Example: "Extract the product name, price, and availability"
        include_tags: CSS selectors for elements to include. Overrides only_main_content.
            Example: ["article", "main", ".content"]
        exclude_tags: CSS selectors for elements to exclude.
            Example: ["nav", "footer", ".sidebar", ".ads"]
        max_age: Cache freshness in seconds. If cached version exists and is fresher,
            return cached result. Set to 0 to always fetch fresh (default).

    Returns:
        Firecrawl-compatible scrape result:
        {
            "success": true,
            "data": {
                "markdown": "...",
                "html": "...",
                "screenshot": "base64...",
                "llm_extraction": {...},  // For json format
                "summary": "...",  // For summary format
                "branding": {...},  // For branding format
                "metadata": {
                    "title": "...",
                    "description": "...",
                    "og_image": "..."
                },
                "links": [...],
                "images": [...]
            }
        }

    Note:
        - The json and summary formats require an LLM. Configure with:
          SUPACRAWL_LLM_PROVIDER (ollama/openai/anthropic)
          SUPACRAWL_LLM_MODEL (e.g., qwen3:8b, gpt-4o-mini)
        - Anti-bot protection is automatic. For heavily protected sites,
          enable stealth mode in config or use a proxy.
    """
    # Generate correlation ID for request tracking
    correlation_id = get_correlation_id() or generate_correlation_id()

    try:
        # Validate inputs
        validated_url = validate_url(url)
        assert validated_url is not None  # validate_url raises on None
        validated_timeout = validate_timeout(timeout, "timeout") or 30000

        if formats is None:
            formats = ["markdown"]

        # Convert action dicts to Action objects if provided
        action_objects = None
        if actions:
            from supacrawl.services.actions import Action

            action_objects = [
                Action(
                    type=a.get("type", "wait"),
                    selector=a.get("selector"),
                    milliseconds=a.get("milliseconds"),
                    text=a.get("text"),
                    direction=a.get("direction"),
                    key=a.get("key"),
                    script=a.get("script"),
                    full_page=bool(a.get("fullPage", a.get("full_page", True))),
                )
                for a in actions
            ]

        result = await api_client.scrape_service.scrape(
            url=validated_url,
            formats=formats,
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=validated_timeout,
            screenshot_full_page=screenshot_full_page,
            actions=action_objects,
            json_schema=json_schema,
            json_prompt=json_prompt,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            max_age=max_age,
        )

        response = result.model_dump()
        response["correlation_id"] = correlation_id
        return response

    except SupacrawlValidationError:
        raise
    except Exception as e:
        log_tool_exception("supacrawl_scrape", e)
        raise map_exception(e, endpoint="/scrape", correlation_id=correlation_id) from e
