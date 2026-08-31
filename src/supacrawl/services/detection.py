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
# Visible body text ceiling for the script-heavy shell guard (Guard 3).
# 100–499 chars of visible text on a script-heavy page is intentionally
# treated as a probable JS shell: that range is consistent with a nav+footer
# wrapper where the real content is injected at runtime, not with a page that
# has actual written content. Pages at or above 500 chars are left alone even
# when they carry large analytics or config blobs.
_JS_SHELL_MAX_VISIBLE_TEXT = 500
# Minimum ratio of inline executable-JS chars to visible text chars for Guard 3.
# A ratio ≥ 3 means the document's bulk is script, not content — a strong
# signal that the real content is injected at runtime.
_JS_SHELL_SCRIPT_TEXT_RATIO = 3
# Matches only executable JavaScript <script> blocks for Guard 3 script_chars.
# Excludes type values containing "json" (application/ld+json, application/json)
# and "template" (text/template, text/x-handlebars-template, etc.) because these
# are static structured-data or server-side-template annotations present on many
# genuine static pages — counting them would falsely escalate a product page
# carrying a schema.org block.
_JS_EXECUTABLE_SCRIPT_RE = re.compile(
    r'<script(?![^>]*\s+type\s*=\s*["\'][^"\']*(?:json|template)[^"\']*["\'])[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


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

        # Collect executable-JS script content before stripping, so Guard 3
        # can measure it. See _JS_EXECUTABLE_SCRIPT_RE for exclusion rationale.
        script_blocks = _JS_EXECUTABLE_SCRIPT_RE.findall(body_content)
        script_chars = sum(len(s) for s in script_blocks)

        body_text = re.sub(r"<script[^>]*>.*?</script>", "", body_content, flags=re.DOTALL | re.IGNORECASE)
        body_text = re.sub(r"<style[^>]*>.*?</style>", "", body_text, flags=re.DOTALL | re.IGNORECASE)
        body_text = re.sub(r"<[^>]+>", "", body_text)
        body_text = body_text.strip()

        # Guard 2: visible text so sparse that the body carries no real content.
        if len(body_text) < _MIN_BODY_TEXT_LENGTH:
            return True

        # Guard 3: thin visible text with a script payload that dwarfs it.
        # Catches SPA shells that ship all data inline (e.g. a JSON quote array)
        # without any recognised framework marker — a static GET returns only
        # the nav/footer wrapper while the real content is injected at runtime.
        # The _JS_SHELL_MAX_VISIBLE_TEXT ceiling prevents escalating content-rich
        # pages that happen to carry large analytics or config blobs.
        if len(body_text) < _JS_SHELL_MAX_VISIBLE_TEXT and script_chars >= len(body_text) * _JS_SHELL_SCRIPT_TEXT_RATIO:
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


# Navigation-chrome class signals. Kept identical to the `isNavChrome` regex in
# BrowserManager._expand_disclosures — the browser decides what it will expand,
# and this function decides whether that is worth a browser, so the two must
# agree about what counts as a site menu.
_NAV_CHROME_CLASS_RE = re.compile(
    r"\b(hamburger|mobile-nav|site-nav|main-nav|primary-nav|mega-menu|dropdown-nav"
    r"|nav-menu|menu-toggle|topnav|global-nav|utility-nav|nav__toggle|breadcrumb|toc-toggle)\b"
)
_NAV_CHROME_ROLES = frozenset({"navigation", "menubar", "menu"})


def _attr_str(element: Any, name: str) -> str:
    """Return an element's attribute as a string.

    BeautifulSoup hands back a list for attributes it treats as multi-valued,
    so a bare `.strip()` on the result is a latent AttributeError. Joining is
    the honest normalisation: both spellings mean the same thing to a selector.
    """
    value = element.get(name)
    if isinstance(value, list):
        return " ".join(value)
    return value or ""


def _is_nav_chrome(element: Any) -> bool:
    """True when an element sits inside site navigation rather than content.

    Mirrors the browser-side `isNavChrome` walk: a `<nav>` ancestor, a
    navigation/menu ARIA role, or a nav-flavoured class anywhere up the tree.
    Excluding these is what stops a hamburger button — which is a collapsed
    disclosure by the letter of the markup — from dragging every page with a
    mobile menu into the browser.
    """
    for node in [element, *element.parents]:
        if getattr(node, "name", None) == "nav":
            return True
        role = _attr_str(node, "role") if hasattr(node, "get") else ""
        if role.lower() in _NAV_CHROME_ROLES:
            return True
        classes = node.get("class") or [] if hasattr(node, "get") else []
        if _NAV_CHROME_CLASS_RE.search(" ".join(classes).lower()):
            return True
    return False


_FORM_CONTROL_TAGS = frozenset({"input", "select", "textarea"})

# A disclosure whose text is almost entirely link text is a table of contents or
# a menu — navigation that simply carries no nav tag, role or class to say so.
# Opening it adds a link list the page's own markup already yields, so it is not
# worth a browser render. Measured against peps.python.org, whose closed
# "Table of Contents" <details> sits in <main> with no class at all: 0.98.
_LINK_LIST_TEXT_RATIO = 0.9
_LINK_LIST_MIN_LINKS = 3


def _is_link_list(element: Any) -> bool:
    """True when a disclosure's hidden content is essentially a list of links.

    A <summary> is the always-visible label, never part of what opening the
    element reveals, so it is excluded from both sides of the ratio — counting
    it would let a long label disguise a short menu as content.
    """
    links = element.find_all("a")
    if len(links) < _LINK_LIST_MIN_LINKS:
        return False
    summary = element.find("summary")
    summary_text = summary.get_text(" ", strip=True) if summary else ""
    text = element.get_text(" ", strip=True)
    revealed = len(text) - len(summary_text)
    if revealed <= 0:
        return False
    link_text = " ".join(
        a.get_text(" ", strip=True) for a in links if summary is None or a.find_parent("summary") is None
    )
    return len(link_text) / revealed >= _LINK_LIST_TEXT_RATIO


def _is_hidden_from_the_fast_path(element: Any) -> bool:
    """True when the markdown converter would strip this element's text.

    Mirrors the hiding mechanisms in `MarkdownConverter.BOILERPLATE_SELECTORS`
    — `[hidden]`, `.hidden`, and an inline `display:none`. Those are the only
    ways a panel present in the HTML is nonetheless absent from the fast path's
    OUTPUT, and matching that list is what keeps this predicate honest: a panel
    the converter already emits is not gated, however collapsed its ARIA state
    claims to be.
    """
    for node in [element, *element.parents]:
        if not hasattr(node, "get"):
            continue
        if node.has_attr("hidden"):
            return True
        if "hidden" in (node.get("class") or []):
            return True
        if "display:none" in _attr_str(node, "style").replace(" ", ""):
            return True
    return False


def detect_collapsed_disclosures(html: str) -> bool:
    """True when a disclosure hides content the HTTP-first path would MISS.

    The browser path always runs `BrowserManager._expand_disclosures`, which
    clicks collapsed `aria-expanded="false"` controls so click-gated content
    lands in the captured HTML. A page satisfied by the fast path never reaches
    that step (#142).

    The question is deliberately not "is anything collapsed?" — measured
    against the real converter, a closed `<details>` and a Bootstrap
    `.collapse` panel both have their text emitted into the fast path's
    markdown already, because the converter is an HTML-to-text pass and neither
    mechanism hides anything from it. Escalating for those would buy no content
    and cost a browser render on a large fraction of the web, `<details>` and
    Bootstrap accordions being as common as they are.

    Content is genuinely missing from the fast path in exactly two cases, and
    only these escalate:

    - The panel is not in the DOM at all — the site injects it on first click,
      so `aria-controls` names an id nothing matches.
    - The panel is present but hidden by a mechanism the converter strips
      (`[hidden]`, `.hidden`, inline `display:none`).

    Args:
        html: Raw HTML from the HTTP-first fetch.

    Returns:
        True when at least one disclosure outside navigation chrome hides
        content the fast path would not otherwise capture.
    """
    # Substring pre-check first: pages with no ARIA disclosure markup — the
    # overwhelming majority — pay one scan and never build a parse tree.
    #
    # Matched on the bare attribute name, never on `aria-expanded="false"`:
    # single quotes and whitespace around the `=` are both valid HTML, so a
    # spelling-specific probe would short-circuit to False on a page the parse
    # below would have caught. The value is checked by the selector.
    if "aria-expanded" not in html.lower():
        return False

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    for control in soup.select('[aria-expanded="false"]'):
        # `aria-controls` is the spec signal for a genuine disclosure widget.
        # Without it a bare action button (sort, filter, load-more) that uses
        # aria-expanded as a state flag would count.
        target_id = _attr_str(control, "aria-controls").strip()
        if not target_id:
            continue
        # A form control carrying aria-expanded is the ARIA *combobox* pattern —
        # a search box whose suggestions appear as you type. The expander clicks
        # it and reveals nothing, so escalating for one is pure cost.
        if control.name in _FORM_CONTROL_TAGS:
            continue
        if _attr_str(control, "type").lower() in ("submit", "reset"):
            continue
        if _is_nav_chrome(control):
            continue

        target = soup.find(id=target_id)
        if target is None:
            # Injected on first click: the content is not in this HTML at all,
            # which is the case the fast path can never satisfy.
            return True
        if not _is_hidden_from_the_fast_path(target):
            # Already in the converter's output — a browser adds nothing.
            continue
        if _is_link_list(target) or _is_nav_chrome(target):
            # A hidden menu is still a menu.
            continue
        return True

    return False
