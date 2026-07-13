"""Diagnostic tool for troubleshooting scrape issues."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from supacrawl.services.detection import (
    detect_bot_protection,
    detect_cdn,
    detect_js_framework,
    detect_login_required,
    estimate_js_requirement,
    generate_recommendations,
)
from supacrawl.services.validation import validate_url

if TYPE_CHECKING:
    from supacrawl.services.registry import SupacrawlServices

logger = logging.getLogger(__name__)


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
    # Validate URL
    validated_url = validate_url(url)
    assert validated_url is not None

    diagnosis: dict[str, Any] = {
        "url": validated_url,
        "reachable": False,
        "http_status": None,
        "response_time_ms": None,
        "content_type": None,
        "content_length": None,
        "indicators": {},
        "recommendations": {},
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        ) as client:
            start_time = time.perf_counter()
            response = await client.get(validated_url)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            diagnosis["reachable"] = True
            diagnosis["http_status"] = response.status_code
            diagnosis["response_time_ms"] = round(elapsed_ms)

            # Extract headers
            headers = dict(response.headers)
            content_type = headers.get("content-type", "").split(";")[0].strip()
            diagnosis["content_type"] = content_type

            # Get content length
            content_length = response.headers.get("content-length")
            if content_length:
                diagnosis["content_length"] = int(content_length)
            else:
                diagnosis["content_length"] = len(response.content)

            # Only analyse HTML content
            if "html" in content_type.lower():
                html = response.text

                # Detect indicators
                cdn = detect_cdn(headers)
                framework = detect_js_framework(html)
                bot_indicators = detect_bot_protection(html)
                login_required = detect_login_required(html)
                requires_js = estimate_js_requirement(html, diagnosis["content_length"])

                diagnosis["indicators"] = {
                    "cdn_detected": cdn,
                    "js_framework": framework,
                    "requires_javascript": requires_js,
                    "login_required": login_required,
                    **bot_indicators,
                }

                # Generate recommendations
                diagnosis["recommendations"] = generate_recommendations(
                    cdn=cdn,
                    framework=framework,
                    bot_indicators=bot_indicators,
                    requires_js=requires_js,
                    login_required=login_required,
                )
            else:
                diagnosis["indicators"] = {"non_html_content": True}
                diagnosis["recommendations"] = {"reason": f"Non-HTML content type: {content_type}"}

    except httpx.TimeoutException:
        diagnosis["error"] = "timeout"
        diagnosis["recommendations"] = {
            "wait_for": 5000,
            "reason": "URL timed out - may need longer timeout or be slow/unresponsive",
        }
    except httpx.ConnectError as e:
        diagnosis["error"] = "connection_failed"
        diagnosis["error_detail"] = str(e)
        diagnosis["recommendations"] = {
            "reason": "Could not connect to URL - check if URL is correct and accessible",
        }
    except Exception as e:
        logger.debug(f"Diagnose failed for {url}: {e}")
        diagnosis["error"] = "diagnosis_failed"
        diagnosis["error_detail"] = str(e)

    return {"success": True, "diagnosis": diagnosis}
