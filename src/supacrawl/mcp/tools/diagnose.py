"""FastMCP-facing wrapper around ``supacrawl.services.diagnose``.

Translates the portable core function's exceptions into the MCP typed
exception hierarchy so FastMCP surfaces a real message to the LLM instead of
a masked ``Error calling tool`` when ``mask_error_details=True``.
"""

from typing import Any

from supacrawl.mcp.exceptions import log_tool_exception, map_exception
from supacrawl.services.diagnose import supacrawl_diagnose as _supacrawl_diagnose
from supacrawl.services.registry import SupacrawlServices


async def supacrawl_diagnose(
    api_client: SupacrawlServices,
    url: str,
) -> dict[str, Any]:
    """
    Diagnose potential issues with scraping a URL.

    Use this BEFORE scraping if you want to understand potential issues,
    or AFTER a failed scrape to understand why it returned empty/minimal content.

    This performs a lightweight check (no browser needed) to detect:
    - CDN/WAF protection (Cloudflare, Akamai, etc.)
    - JavaScript framework requirements (React, Vue, etc.)
    - Bot detection and CAPTCHA presence
    - Login requirements
    - Recommended scrape settings

    Args:
        api_client: Injected SupacrawlServices instance
        url: URL to diagnose

    Returns:
        Diagnostic information including:
        - reachable: Whether the URL is accessible
        - http_status: HTTP response status code
        - response_time_ms: Response time in milliseconds
        - content_type: Content-Type header
        - content_length: Content-Length or actual length
        - indicators: Detection results (CDN, JS framework, bot protection)
        - recommendations: Suggested scrape settings and explanations

    Example:
        # Pre-check before scraping
        result = await supacrawl_diagnose(url="https://example.com")
        if result["indicators"]["requires_javascript"]:
            # Use higher wait_for value
            scrape_result = await supacrawl_scrape(
                url="https://example.com",
                wait_for=result["recommendations"]["wait_for"]
            )
    """
    try:
        return await _supacrawl_diagnose(api_client, url)
    except Exception as e:
        log_tool_exception("supacrawl_diagnose", e)
        raise map_exception(e, endpoint="/diagnose") from e
