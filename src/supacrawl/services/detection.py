"""Pure, network-free heuristics for classifying a fetched page.

These functions inspect response headers and raw HTML to answer questions the
scrape, crawl, and diagnose paths all need: which CDN/WAF is in front of the
site, which JavaScript framework rendered it, whether a browser is required to
see the content, and whether bot protection or a login wall is present.

Everything here is a pure function — no I/O, no logging, no Playwright — so the
HTTP-first fast path (``ScrapeService``), the ``supacrawl_diagnose`` tool, and
remediation-hint generation can share one brain instead of three drifting copies.
"""

import re
from typing import Any

# Known CDN/WAF signatures in response headers.
CDN_SIGNATURES: dict[str, dict[str, list[str]]] = {
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

# JavaScript framework detection patterns, matched against lowercased HTML.
JS_FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "react": [
        r'<div id="root"></div>',
        r'<div id="app"></div>',
        r"data-reactroot",
        r"__next_data__",
        r"_next/static",
    ],
    "vue": [
        r'<div id="app"></div>',
        r"__nuxt__",
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

# Minimum rendered-body text length below which a page is assumed to need JS.
_MIN_BODY_TEXT_LENGTH = 100
# HTML length below which a framework marker is treated as a JS-shell signal.
_JS_SHELL_HTML_LENGTH = 5000


def detect_cdn(headers: dict[str, str]) -> str | None:
    """Detect the CDN/WAF in front of a site from its response headers.

    Args:
        headers: Response headers (case-insensitive keys are handled).

    Returns:
        The CDN identifier (e.g. ``"cloudflare"``) or ``None`` when no known
        signature matches.
    """
    headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

    for cdn_name, signatures in CDN_SIGNATURES.items():
        for sig_header in signatures["headers"]:
            if sig_header.lower() in headers_lower:
                return cdn_name

        server = headers_lower.get("server", "")
        for sig_server in signatures["server"]:
            if sig_server in server:
                return cdn_name

    return None


def detect_js_framework(html: str) -> str | None:
    """Detect a client-side JavaScript framework from page markup.

    Args:
        html: Raw HTML content.

    Returns:
        The framework name (``"react"``, ``"vue"``, ``"angular"``, ``"svelte"``)
        or ``None`` when no marker is found.
    """
    html_lower = html.lower()

    for framework, patterns in JS_FRAMEWORK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, html_lower, re.IGNORECASE):
                return framework

    return None


def detect_bot_protection(html: str) -> dict[str, Any]:
    """Detect bot-protection, CAPTCHA, and access-denied signals in HTML.

    Args:
        html: Raw HTML content.

    Returns:
        A dict with boolean keys ``captcha_present``, ``challenge_detected``,
        and ``access_denied``.
    """
    html_lower = html.lower()

    indicators: dict[str, Any] = {
        "captcha_present": False,
        "challenge_detected": False,
        "access_denied": False,
    }

    captcha_patterns = ["g-recaptcha", "h-captcha", "cf-turnstile", "captcha"]
    for pattern in captcha_patterns:
        if pattern in html_lower:
            indicators["captcha_present"] = True
            break

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

    denied_patterns = ["access denied", "403 forbidden", "blocked"]
    for pattern in denied_patterns:
        if pattern in html_lower:
            indicators["access_denied"] = True
            break

    return indicators


def detect_login_required(html: str) -> bool:
    """Detect whether a page likely requires authentication.

    Args:
        html: Raw HTML content.

    Returns:
        True when login indicators (sign-in links, password fields) are present.
    """
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
    return any(pattern in html_lower for pattern in login_patterns)


def estimate_js_requirement(html: str, content_length: int) -> bool:
    """Estimate whether a page needs JavaScript rendering to show its content.

    This is the render-needed heuristic that lets the HTTP-first fast path
    decide when a cheap httpx GET is enough and when it must escalate to a
    full browser render.

    Args:
        html: Raw HTML content.
        content_length: Length of the response body in bytes/characters.

    Returns:
        True when the page appears to be a JS shell that needs a browser.
    """
    # A framework marker in a small document is a strong JS-shell signal.
    framework = detect_js_framework(html)
    if framework and content_length < _JS_SHELL_HTML_LENGTH:
        return True

    # An effectively empty <body> (once scripts/styles/tags are stripped) means
    # the real content is injected client-side.
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if body_match:
        body_content = body_match.group(1).strip()
        body_text = re.sub(r"<script[^>]*>.*?</script>", "", body_content, flags=re.DOTALL | re.IGNORECASE)
        body_text = re.sub(r"<style[^>]*>.*?</style>", "", body_text, flags=re.DOTALL | re.IGNORECASE)
        body_text = re.sub(r"<[^>]+>", "", body_text)
        body_text = body_text.strip()

        if len(body_text) < _MIN_BODY_TEXT_LENGTH:
            return True

    return False


def generate_recommendations(
    cdn: str | None,
    framework: str | None,
    bot_indicators: dict[str, Any],
    requires_js: bool,
    login_required: bool,
) -> dict[str, Any]:
    """Turn detection signals into actionable scrape recommendations.

    Args:
        cdn: Detected CDN/WAF name, or None.
        framework: Detected JS framework name, or None.
        bot_indicators: Output of :func:`detect_bot_protection`.
        requires_js: Output of :func:`estimate_js_requirement`.
        login_required: Output of :func:`detect_login_required`.

    Returns:
        A dict of recommended settings (``engine``, ``stealth_mode``,
        ``wait_for``, ``captcha_solving``, ``proxy``, ``auth_required``) plus a
        human-readable ``reason`` string.
    """
    recommendations: dict[str, Any] = {}
    reasons: list[str] = []

    wait_for = 0

    if requires_js or framework:
        wait_for = max(wait_for, 3000)
        reasons.append(f"JavaScript rendering required{f' ({framework} detected)' if framework else ''}")

    if cdn == "akamai":
        recommendations["engine"] = "camoufox"
        recommendations["stealth_mode"] = True
        wait_for = max(wait_for, 5000)
        reasons.append(
            "Akamai Bot Manager detected - use --engine camoufox for best results "
            "(requires: pip install supacrawl[camoufox])"
        )
    elif cdn == "cloudflare" or bot_indicators.get("challenge_detected"):
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
