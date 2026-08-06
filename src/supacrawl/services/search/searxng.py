"""SearXNG search provider implementation.

SearXNG is a free, self-hosted metasearch engine. It aggregates results
from multiple search engines without tracking users.

Configuration:
    SEARXNG_URL       Instance URL, carrying no credentials.
                      Example: SEARXNG_URL=https://searxng.example.invalid
    SEARXNG_USERNAME  HTTP Basic username, when the instance sits behind a
                      Basic-auth gate. Optional — an ungated instance needs
                      neither this nor SEARXNG_PASSWORD.
    SEARXNG_PASSWORD  HTTP Basic password. Optional, paired with the above.

Deprecated: embedding the credential in the URL as ``https://user:pass@host``.
That shape makes the whole URL a secret, which is a materially worse property
than it looks: any config renderer that resolves ``${SEARXNG_URL}`` prints the
password wherever it renders, and httpx quotes the request URL verbatim into
its own error messages, so a single 401 puts the password in the logs. The
shape is still honoured so an installation configured that way keeps working,
but the credential is split out of the URL at construction — the URL that
reaches the wire, the logs, and any error message never carries userinfo.
Prefer SEARXNG_USERNAME / SEARXNG_PASSWORD, which win when both are set.
"""

import logging
import os
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from supacrawl.models import SearchFilters, SearchResultItem, SearchSourceType
from supacrawl.services.search.filters import domain_operator_query
from supacrawl.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


def _split_url_credentials(url: str) -> tuple[str, httpx.BasicAuth | None]:
    """Split any ``user:pass@`` userinfo out of an instance URL.

    Args:
        url: Instance URL, which may carry userinfo in the deprecated shape.

    Returns:
        The URL with userinfo removed, plus the Basic credential it carried
        (None when there was none). Callers apply the credential explicitly so
        the URL itself is safe to log, quote in an error, or hand to httpx.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        # A URL malformed enough to fail parsing has no recoverable userinfo;
        # leave it untouched so it fails at request time as it always did.
        return url, None

    if parts.username is None and parts.password is None:
        return url, None

    host = parts.hostname or ""
    # urlsplit strips the brackets an IPv6 literal needs in an authority, and a
    # bare hostname can never contain a colon (the port is split off already),
    # so a colon here means IPv6 and the brackets must go back on.
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{parts.port}" if parts.port else host
    clean = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    auth = httpx.BasicAuth(unquote(parts.username or ""), unquote(parts.password or ""))
    return clean, auth


class SearXNGProvider:
    """SearXNG metasearch engine provider.

    Requires a SEARXNG_URL pointing to a running SearXNG instance.
    Supports web, image, and news search via SearXNG categories.

    An instance behind an HTTP Basic gate takes its credential from
    SEARXNG_USERNAME / SEARXNG_PASSWORD (or the matching constructor
    arguments), applied per request rather than on the HTTP client — the client
    is shared with every other provider, so a credential set on it would be
    sent to every other search backend too.
    """

    def __init__(
        self,
        url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        resolved = url or os.getenv("SEARXNG_URL", "") or ""
        clean_url, url_auth = _split_url_credentials(resolved.rstrip("/"))
        self._url = clean_url.rstrip("/")

        explicit_username = username if username is not None else os.getenv("SEARXNG_USERNAME") or None
        explicit_password = password if password is not None else os.getenv("SEARXNG_PASSWORD") or None
        if explicit_username and explicit_password:
            self._auth: httpx.BasicAuth | None = httpx.BasicAuth(explicit_username, explicit_password)
        else:
            if explicit_username or explicit_password:
                missing = "SEARXNG_PASSWORD" if explicit_username else "SEARXNG_USERNAME"
                # Say what will ACTUALLY happen: a URL still carrying userinfo
                # takes over, so "nothing will be sent" would send an operator
                # debugging this config down the wrong path entirely.
                outcome = (
                    "the deprecated credential embedded in SEARXNG_URL is being used instead"
                    if url_auth is not None
                    else "no credential will be sent"
                )
                LOGGER.warning(
                    "SearXNG HTTP Basic auth is half-configured: %s is not set, so %s. "
                    "Set both SEARXNG_USERNAME and SEARXNG_PASSWORD, or neither.",
                    missing,
                    outcome,
                )
            self._auth = url_auth

        self._owns_client = http_client is None
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "searxng"

    def is_available(self) -> bool:
        return bool(self._url)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
            self._owns_client = True
        return self._http_client

    async def _search(
        self,
        query: str,
        limit: int,
        categories: str,
        correlation_id: str,
        filters: SearchFilters | None = None,
    ) -> list[dict]:
        """Execute a search against the SearXNG JSON API."""
        client = await self._get_client()
        if filters and not filters.is_empty():
            query = domain_operator_query(query, filters.include_domains, filters.exclude_domains)
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "categories": categories,
        }
        # SearXNG supports day/month/year but not week.
        if filters and filters.time_range and filters.time_range in ("day", "month", "year"):
            params["time_range"] = filters.time_range
        # Per-request, never on the client: ``client`` is shared with every other
        # provider in the chain, so setting ``client.auth`` would send this
        # instance's credential to Brave, Tavily, Serper and the rest.
        response = await client.get(
            f"{self._url}/search",
            params=params,
            auth=self._auth,
        )
        response.raise_for_status()

        data = response.json()
        return data.get("results", [])[:limit]

    async def search_web(
        self, query: str, limit: int, correlation_id: str, filters: SearchFilters | None = None
    ) -> list[SearchResultItem]:
        raw_results = await self._search(query, limit, "general", correlation_id, filters)
        results: list[SearchResultItem] = []
        for item in raw_results:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("content", ""),
                    source_type=SearchSourceType.WEB,
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"SearXNG returned {len(results)} web results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def search_images(
        self, query: str, limit: int, correlation_id: str, filters: SearchFilters | None = None
    ) -> list[SearchResultItem]:
        raw_results = await self._search(query, limit, "images", correlation_id)
        results: list[SearchResultItem] = []
        for item in raw_results:
            results.append(
                SearchResultItem(
                    url=item.get("url", item.get("img_src", "")),
                    title=item.get("title", ""),
                    description=item.get("content", item.get("source", "")),
                    source_type=SearchSourceType.IMAGES,
                    thumbnail=item.get("thumbnail_src", item.get("img_src", "")),
                    image_width=item.get("img_format", {}).get("width")
                    if isinstance(item.get("img_format"), dict)
                    else None,
                    image_height=item.get("img_format", {}).get("height")
                    if isinstance(item.get("img_format"), dict)
                    else None,
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"SearXNG returned {len(results)} image results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def search_news(
        self, query: str, limit: int, correlation_id: str, filters: SearchFilters | None = None
    ) -> list[SearchResultItem]:
        raw_results = await self._search(query, limit, "news", correlation_id, filters)
        results: list[SearchResultItem] = []
        for item in raw_results:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("content", ""),
                    source_type=SearchSourceType.NEWS,
                    published_at=item.get("publishedDate"),
                    source_name=item.get("engine", ""),
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"SearXNG returned {len(results)} news results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def close(self) -> None:
        if self._http_client and self._owns_client:
            await self._http_client.aclose()
            self._http_client = None
