"""HTTP-first fetch: a cheap httpx GET for pages that do not need a browser.

Most pages render their content server-side; launching Playwright for them
wastes seconds and laptop battery. This module performs a single httpx GET so
``ScrapeService`` can try the cheap path first and escalate to a full browser
render only when a render-needed or bot-challenge signal fires.
"""

import logging
from dataclasses import dataclass

import httpx

LOGGER = logging.getLogger(__name__)

# A realistic desktop Chrome UA so static fetches look like an ordinary browser
# rather than a bare HTTP client (which more sites block outright).
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Don't pull multi-megabyte documents over the fast path — the browser handles
# heavy pages. 5 MB is comfortably above any text/HTML article.
DEFAULT_MAX_BYTES = 5 * 1024 * 1024


@dataclass
class HttpFetchResult:
    """Result of a successful HTTP-first fetch.

    Attributes:
        url: Final URL after following redirects.
        html: Decoded response body.
        status_code: HTTP status code.
        content_type: Lowercased content type without parameters.
        headers: Response headers (for CDN detection).
    """

    url: str
    html: str
    status_code: int
    content_type: str
    headers: dict[str, str]


async def fetch_static(
    url: str,
    *,
    timeout_ms: int,
    headers: dict[str, str] | None = None,
    accept_language: str | None = None,
    proxy: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> HttpFetchResult | None:
    """Fetch a URL with a single httpx GET, without a browser.

    Args:
        url: URL to fetch.
        timeout_ms: Total request timeout in milliseconds.
        headers: Caller-supplied headers (e.g. Authorization); these overlay the
            default browser-like headers and win on key collisions.
        accept_language: Accept-Language header value (typically derived from the
            scrape's locale config).
        proxy: Optional proxy URL passed straight to httpx.
        max_bytes: Maximum response body size to accept on the fast path.

    Returns:
        An :class:`HttpFetchResult` for HTML responses, or ``None`` when the fast
        path is not viable (network error, non-HTML content type, or oversized
        body) and the caller should fall back to the browser.
    """
    request_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": accept_language or "en-US,en;q=0.9",
    }
    if headers:
        request_headers.update(headers)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_ms / 1000.0),
            proxy=proxy,
            headers=request_headers,
        ) as client:
            response = await client.get(url)
    except Exception as e:
        # Any transport failure simply disqualifies the fast path; the browser
        # path runs next and produces the real error if it also fails.
        LOGGER.debug("HTTP-first fetch failed for %s: %s", url, e)
        return None

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()

    # Only markup is fast-pathable. PDFs are handled by the dedicated PDF path,
    # and other binary content belongs to the browser.
    if content_type and "html" not in content_type and "xml" not in content_type:
        LOGGER.debug("HTTP-first skipped for %s: non-HTML content type %r", url, content_type)
        return None

    body = response.content
    if len(body) > max_bytes:
        LOGGER.debug("HTTP-first skipped for %s: body %d bytes exceeds %d cap", url, len(body), max_bytes)
        return None

    return HttpFetchResult(
        url=str(response.url),
        html=response.text,
        status_code=response.status_code,
        content_type=content_type,
        headers=dict(response.headers),
    )
