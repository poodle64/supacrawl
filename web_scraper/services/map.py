"""Map service for URL discovery (Firecrawl-compatible)."""

from __future__ import annotations

import logging
from collections import deque
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from web_scraper.services.browser import BrowserManager
from web_scraper.models import MapLink, MapResult

LOGGER = logging.getLogger(__name__)


class MapService:
    """Discover all URLs on a website (Firecrawl-compatible).

    Usage:
        service = MapService()
        result = await service.map("https://example.com")
        for link in result.links:
            print(link.url, link.title)
    """

    def __init__(self, browser: BrowserManager | None = None):
        """Initialize map service.

        Args:
            browser: Optional BrowserManager (created if not provided)
        """
        self._browser = browser
        self._owns_browser = browser is None

    async def map(
        self,
        url: str,
        limit: int = 200,
        max_depth: int = 3,
        sitemap: Literal["include", "skip", "only"] = "include",
        include_subdomains: bool = False,
        search: str | None = None,
    ) -> MapResult:
        """Map a website and discover URLs.

        Args:
            url: Starting URL
            limit: Maximum URLs to return
            max_depth: Maximum BFS depth
            sitemap: Sitemap handling mode
            include_subdomains: Include subdomain URLs
            search: Filter URLs containing this text

        Returns:
            MapResult with discovered links
        """
        try:
            # Parse starting URL for domain
            parsed = urlparse(url)
            domain = parsed.netloc

            # Collect URLs from different sources
            discovered_urls: set[str] = set()

            # Fetch sitemap URLs if requested
            if sitemap != "skip":
                LOGGER.info(f"Fetching sitemap from {url}")
                sitemap_urls = await self._fetch_sitemap(url)
                discovered_urls.update(sitemap_urls)
                LOGGER.info(f"Found {len(sitemap_urls)} URLs from sitemap")

            # BFS crawl if requested
            if sitemap != "only":
                LOGGER.info(f"Starting BFS crawl from {url}")
                crawl_urls = await self._bfs_crawl(
                    start_url=url,
                    domain=domain,
                    max_depth=max_depth,
                    limit=limit,
                    include_subdomains=include_subdomains,
                )
                discovered_urls.update(crawl_urls)
                LOGGER.info(f"Found {len(crawl_urls)} URLs from crawling")

            # Convert to list and apply limit
            urls_list = list(discovered_urls)[:limit]

            # Apply search filter if provided
            if search:
                urls_list = [u for u in urls_list if search.lower() in u.lower()]
                LOGGER.info(f"Filtered to {len(urls_list)} URLs matching '{search}'")

            # Extract metadata for each URL
            LOGGER.info(f"Extracting metadata for {len(urls_list)} URLs")
            links = []
            for url_str in urls_list:
                title, description = await self._extract_metadata(url_str)
                links.append(MapLink(url=url_str, title=title, description=description))

            return MapResult(success=True, links=links, error=None)

        except Exception as e:
            LOGGER.error(f"Map failed: {e}", exc_info=True)
            return MapResult(success=False, links=[], error=str(e))

    async def _fetch_sitemap(self, base_url: str) -> list[str]:
        """Fetch and parse sitemap.xml.

        Args:
            base_url: Base URL of the site

        Returns:
            List of URLs from sitemap
        """
        urls: list[str] = []
        sitemap_candidates = [
            urljoin(base_url, "/sitemap.xml"),
            urljoin(base_url, "/sitemap_index.xml"),
        ]

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for sitemap_url in sitemap_candidates:
                try:
                    LOGGER.debug(f"Trying sitemap: {sitemap_url}")
                    resp = await client.get(sitemap_url)
                    if resp.status_code == 200:
                        urls.extend(await self._parse_sitemap_xml(client, resp.text))
                except Exception as e:
                    LOGGER.debug(f"Sitemap fetch failed for {sitemap_url}: {e}")

        return list(set(urls))  # Deduplicate

    async def _parse_sitemap_xml(
        self, client: httpx.AsyncClient, xml_content: str
    ) -> list[str]:
        """Parse sitemap XML and extract URLs.

        Args:
            client: HTTP client for fetching nested sitemaps
            xml_content: XML content to parse

        Returns:
            List of URLs found
        """
        urls: list[str] = []
        try:
            soup = BeautifulSoup(xml_content, "xml")

            # Handle sitemap index (nested sitemaps)
            for sitemap_tag in soup.find_all("sitemap"):
                loc = sitemap_tag.find("loc")
                if loc and loc.text:
                    try:
                        LOGGER.debug(f"Fetching nested sitemap: {loc.text}")
                        resp = await client.get(loc.text.strip())
                        if resp.status_code == 200:
                            nested_urls = await self._parse_sitemap_xml(
                                client, resp.text
                            )
                            urls.extend(nested_urls)
                    except Exception as e:
                        LOGGER.debug(f"Failed to fetch nested sitemap {loc.text}: {e}")

            # Handle regular sitemap (URL entries)
            for url_tag in soup.find_all("url"):
                loc = url_tag.find("loc")
                if loc and loc.text:
                    urls.append(loc.text.strip())

        except Exception as e:
            LOGGER.debug(f"Failed to parse sitemap XML: {e}")

        return urls

    async def _bfs_crawl(
        self,
        start_url: str,
        domain: str,
        max_depth: int,
        limit: int,
        include_subdomains: bool,
    ) -> list[str]:
        """BFS crawl to discover URLs.

        Args:
            start_url: Starting URL
            domain: Base domain to stay within
            max_depth: Maximum depth
            limit: Maximum URLs to discover
            include_subdomains: Include subdomains

        Returns:
            List of discovered URLs
        """
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        discovered: list[str] = []

        # Create or use existing browser
        browser = self._browser
        close_browser = False
        if browser is None:
            browser = BrowserManager()
            close_browser = True

        try:
            # Ensure browser is started
            if browser._browser is None:
                await browser.__aenter__()

            while queue and len(discovered) < limit:
                url, depth = queue.popleft()

                # Skip if already visited
                if url in visited:
                    continue
                visited.add(url)

                # Check domain boundaries
                if not self._is_same_domain(url, domain, include_subdomains):
                    continue

                # Add to discovered list
                discovered.append(url)
                LOGGER.debug(
                    f"Discovered [{len(discovered)}/{limit}] depth={depth}: {url}"
                )

                # Extract links if we haven't reached max depth
                if depth < max_depth:
                    try:
                        links = await browser.extract_links(url)
                        for link in links:
                            # Normalize URL (remove fragments)
                            normalized = link.split("#")[0]
                            if normalized and normalized not in visited:
                                queue.append((normalized, depth + 1))
                    except Exception as e:
                        LOGGER.warning(f"Failed to extract links from {url}: {e}")

        finally:
            if close_browser and browser._browser is not None:
                await browser.__aexit__(None, None, None)

        return discovered

    async def _extract_metadata(self, url: str) -> tuple[str | None, str | None]:
        """Extract title and description from a URL.

        Args:
            url: URL to extract metadata from

        Returns:
            Tuple of (title, description)
        """
        # Create or use existing browser
        browser = self._browser
        close_browser = False
        if browser is None:
            browser = BrowserManager()
            close_browser = True

        try:
            # Ensure browser is started
            if browser._browser is None:
                await browser.__aenter__()

            # Fetch page content
            content = await browser.fetch_page(url, wait_for_spa=False)

            # Extract metadata
            metadata = await browser.extract_metadata(content.html)

            # Prefer og:title/og:description, fall back to regular tags
            title = metadata.og_title or metadata.title
            description = metadata.og_description or metadata.description

            return (title, description)

        except Exception as e:
            LOGGER.warning(f"Failed to extract metadata from {url}: {e}")
            return (None, None)

        finally:
            if close_browser and browser._browser is not None:
                await browser.__aexit__(None, None, None)

    def _is_same_domain(
        self,
        url: str,
        base_domain: str,
        include_subdomains: bool,
    ) -> bool:
        """Check if URL is within the allowed domain.

        Args:
            url: URL to check
            base_domain: Base domain
            include_subdomains: Include subdomains

        Returns:
            True if URL is within domain
        """
        try:
            parsed = urlparse(url)
            url_domain = parsed.netloc.lower()
            base = base_domain.lower()

            if include_subdomains:
                # Allow exact match or subdomain
                return url_domain == base or url_domain.endswith(f".{base}")
            else:
                # Exact match only
                return url_domain == base

        except Exception:
            return False
