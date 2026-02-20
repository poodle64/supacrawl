"""Diagnostic tool for troubleshooting scrape issues."""

import re
import time
from typing import Any

import httpx

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.config import logger
from supacrawl.mcp.validators import validate_url

# Known CDN/WAF signatures in headers or content
CDN_SIGNATURES = {
    "cloudflare": {
        "headers": ["cf-ray", "cf-cache-status", "__cf_bm"],
        "server": ["cloudflare"],
    },
    "akamai": {
        "headers": ["x-akamai-transformed", "akamai-origin-hop"],
        "server": ["akamai"],
    },
    "fastly": {
        "headers": ["x-served-by", "x-cache", "fastly-io-info"],
        "server": ["fastly"],
    },
    "aws_cloudfront": {
        "headers": ["x-amz-cf-id", "x-amz-cf-pop"],
        "server": [],
    },
}

# JavaScript framework detection patterns
JS_FRAMEWORK_PATTERNS = {
    "react": [
        r'<div id="root"></div>',
        r'<div id="app"></div>',
        r"data-reactroot",
        r"__NEXT_DATA__",
        r"_next/static",
    ],
    "vue": [
        r'<div id="app"></div>',
        r"__NUXT__",
        r"/_nuxt/",
        r"v-cloak",
    ],
    "angular": [
        r"<app-root",
        r"ng-version",
        r"angular\.min\.js",
    ],
    "svelte": [
        r"svelte-",
        r"__sveltekit",
    ],
}

# Bot detection patterns
BOT_DETECTION_PATTERNS = [
    r"challenge-form",
    r"cf-turnstile",
    r"g-recaptcha",
    r"h-captcha",
    r"captcha",
    r"verify you.*human",
    r"please wait.*checking",
    r"just a moment",
    r"ddos protection",
    r"access denied",
    r"bot detected",
]


def _detect_cdn(headers: dict[str, str]) -> str | None:
    """Detect CDN/WAF from response headers."""
    headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

    for cdn_name, signatures in CDN_SIGNATURES.items():
        # Check for signature headers
        for sig_header in signatures["headers"]:
            if sig_header.lower() in headers_lower:
                return cdn_name

        # Check server header
        server = headers_lower.get("server", "")
        for sig_server in signatures["server"]:
            if sig_server in server:
                return cdn_name

    return None


def _detect_js_framework(html: str) -> str | None:
    """Detect JavaScript framework from HTML content."""
    html_lower = html.lower()

    for framework, patterns in JS_FRAMEWORK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, html_lower, re.IGNORECASE):
                return framework

    return None


def _detect_bot_protection(html: str) -> dict[str, Any]:
    """Detect bot protection and CAPTCHA presence."""
    html_lower = html.lower()

    indicators: dict[str, Any] = {
        "captcha_present": False,
        "challenge_detected": False,
        "access_denied": False,
    }

    # Check for CAPTCHA
    captcha_patterns = ["g-recaptcha", "h-captcha", "cf-turnstile", "captcha"]
    for pattern in captcha_patterns:
        if pattern in html_lower:
            indicators["captcha_present"] = True
            break

    # Check for challenge pages
    challenge_patterns = [
        "just a moment",
        "checking your browser",
        "please wait",
        "verify you",
        "challenge-form",
    ]
    for pattern in challenge_patterns:
        if pattern in html_lower:
            indicators["challenge_detected"] = True
            break

    # Check for access denied
    denied_patterns = ["access denied", "403 forbidden", "blocked"]
    for pattern in denied_patterns:
        if pattern in html_lower:
            indicators["access_denied"] = True
            break

    return indicators


def _detect_login_required(html: str) -> bool:
    """Detect if login is likely required."""
    html_lower = html.lower()
    login_patterns = [
        "sign in",
        "log in",
        "login",
        "please authenticate",
        "access restricted",
        'type="password"',
        "forgot password",
    ]
    for pattern in login_patterns:
        if pattern in html_lower:
            return True
    return False


def _estimate_js_requirement(html: str, content_length: int) -> bool:
    """Estimate if JavaScript rendering is required."""
    # Very short HTML with JS framework detected likely needs JS
    framework = _detect_js_framework(html)
    if framework and content_length < 5000:
        return True

    # Empty body or placeholder content
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if body_match:
        body_content = body_match.group(1).strip()
        # Remove scripts and styles
        body_text = re.sub(r"<script[^>]*>.*?</script>", "", body_content, flags=re.DOTALL | re.IGNORECASE)
        body_text = re.sub(r"<style[^>]*>.*?</style>", "", body_text, flags=re.DOTALL | re.IGNORECASE)
        body_text = re.sub(r"<[^>]+>", "", body_text)
        body_text = body_text.strip()

        # Very little text content suggests JS rendering needed
        if len(body_text) < 100:
            return True

    return False


def _generate_recommendations(
    cdn: str | None,
    framework: str | None,
    bot_indicators: dict[str, Any],
    requires_js: bool,
    login_required: bool,
) -> dict[str, Any]:
    """Generate scrape recommendations based on diagnosis."""
    recommendations: dict[str, Any] = {}
    reasons: list[str] = []

    # Default wait time
    wait_for = 0

    if requires_js or framework:
        wait_for = max(wait_for, 3000)
        reasons.append(f"JavaScript rendering required{f' ({framework} detected)' if framework else ''}")

    if cdn == "cloudflare" or bot_indicators.get("challenge_detected"):
        recommendations["stealth_mode"] = True
        wait_for = max(wait_for, 5000)
        reasons.append("Bot protection detected - stealth mode recommended")

    if bot_indicators.get("captcha_present"):
        recommendations["captcha_solving"] = True
        reasons.append("CAPTCHA detected - may need captcha solving enabled")

    if bot_indicators.get("access_denied"):
        recommendations["proxy"] = True
        reasons.append("Access denied - try with proxy or different IP")

    if login_required:
        recommendations["auth_required"] = True
        reasons.append("Login appears required - scraping may return login page only")

    if wait_for > 0:
        recommendations["wait_for"] = wait_for

    recommendations["reason"] = "; ".join(reasons) if reasons else "No issues detected"

    return recommendations


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
                cdn = _detect_cdn(headers)
                framework = _detect_js_framework(html)
                bot_indicators = _detect_bot_protection(html)
                login_required = _detect_login_required(html)
                requires_js = _estimate_js_requirement(html, diagnosis["content_length"])

                diagnosis["indicators"] = {
                    "cdn_detected": cdn,
                    "js_framework": framework,
                    "requires_javascript": requires_js,
                    "login_required": login_required,
                    **bot_indicators,
                }

                # Generate recommendations
                diagnosis["recommendations"] = _generate_recommendations(
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
