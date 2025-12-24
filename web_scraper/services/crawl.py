"""Crawl service for full-site scraping (Firecrawl-compatible)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator
from urllib.parse import urlparse

from web_scraper.models import CrawlEvent, ScrapeData
from web_scraper.services.browser import BrowserManager
from web_scraper.services.map import MapService
from web_scraper.services.scrape import ScrapeService

if TYPE_CHECKING:
    from web_scraper.corpus.adapter import OutputAdapter

LOGGER = logging.getLogger(__name__)


class CrawlService:
    """Crawl entire websites by combining map and scrape (Firecrawl-compatible).

    Usage:
        service = CrawlService()
        async for event in service.crawl("https://example.com"):
            if event.type == "page":
                print(f"Scraped: {event.url}")
            elif event.type == "progress":
                print(f"Progress: {event.completed}/{event.total}")
    """

    def __init__(self):
        """Initialize crawl service."""
        self._browser: BrowserManager | None = None
        self._map_service: MapService | None = None
        self._scrape_service: ScrapeService | None = None

    async def crawl(
        self,
        url: str,
        limit: int = 100,
        max_depth: int = 3,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        output_dir: Path | None = None,
        resume: bool = False,
        formats: list[str] | None = None,
        output_adapter: OutputAdapter | None = None,
    ) -> AsyncGenerator[CrawlEvent, None]:
        """Crawl a website, yielding events as pages complete.

        Args:
            url: Starting URL
            limit: Maximum pages to crawl
            max_depth: Maximum crawl depth
            include_patterns: URL patterns to include
            exclude_patterns: URL patterns to exclude
            output_dir: Directory to save scraped content (simple flat output)
            resume: Resume from previous crawl state
            formats: Output formats to save (default: ["markdown"])
            output_adapter: Optional OutputAdapter for corpus output with manifests

        Yields:
            CrawlEvent for each page and progress update
        """
        self._formats = formats or ["markdown"]
        self._output_adapter = output_adapter

        try:
            # Start output adapter if provided
            if output_adapter:
                await output_adapter.start()

            # Initialize browser and services
            async with BrowserManager() as browser:
                self._browser = browser
                self._map_service = MapService(browser=browser)
                self._scrape_service = ScrapeService(browser=browser)

                # Load resume state
                scraped_urls: set[str] = set()
                if output_adapter:
                    # Get resume URLs from adapter (handles corpus resume)
                    scraped_urls = output_adapter.get_resume_urls()
                    if scraped_urls:
                        LOGGER.info(f"Resuming crawl with {len(scraped_urls)} already scraped")
                elif resume and output_dir:
                    # Legacy: load from simple manifest
                    scraped_urls = self._load_resume_state(output_dir)
                    LOGGER.info(f"Resuming crawl with {len(scraped_urls)} already scraped")

                # Discover URLs
                LOGGER.info(f"Mapping URLs from {url}")
                map_result = await self._map_service.map(
                    url=url,
                    limit=limit,
                    max_depth=max_depth,
                )

                if not map_result.success:
                    yield CrawlEvent(
                        type="error",
                        error=f"Map failed: {map_result.error}",
                    )
                    return

                # Filter URLs
                urls_to_scrape = []
                for link in map_result.links:
                    if link.url in scraped_urls:
                        continue
                    if include_patterns and not self._matches_patterns(
                        link.url, include_patterns
                    ):
                        continue
                    if exclude_patterns and self._matches_patterns(link.url, exclude_patterns):
                        continue
                    urls_to_scrape.append(link.url)

                total = len(urls_to_scrape)
                LOGGER.info(f"Found {total} URLs to scrape")

                yield CrawlEvent(
                    type="progress",
                    completed=0,
                    total=total,
                )

                # Scrape each URL
                completed = 0
                errors = []

                for url_to_scrape in urls_to_scrape:
                    try:
                        # Map output formats to scrape formats
                        scrape_formats = []
                        if "markdown" in self._formats or "json" in self._formats:
                            scrape_formats.append("markdown")
                        if "html" in self._formats or "json" in self._formats:
                            scrape_formats.append("html")
                        if not scrape_formats:
                            scrape_formats = ["markdown"]

                        result = await self._scrape_service.scrape(
                            url_to_scrape,
                            formats=scrape_formats,  # type: ignore[arg-type]
                        )

                        if result.success and result.data:
                            # Save to output adapter (corpus) or directory (simple)
                            if output_adapter:
                                await output_adapter.write_page(url_to_scrape, result)
                            elif output_dir:
                                self._save_page(output_dir, url_to_scrape, result.data)

                            yield CrawlEvent(
                                type="page",
                                url=url_to_scrape,
                                data=result.data,
                                completed=completed + 1,
                                total=total,
                            )
                        else:
                            errors.append(f"{url_to_scrape}: {result.error}")
                            yield CrawlEvent(
                                type="error",
                                url=url_to_scrape,
                                error=result.error,
                                completed=completed + 1,
                                total=total,
                            )

                    except Exception as e:
                        errors.append(f"{url_to_scrape}: {str(e)}")
                        LOGGER.error(f"Scrape failed for {url_to_scrape}: {e}")
                        yield CrawlEvent(
                            type="error",
                            url=url_to_scrape,
                            error=str(e),
                            completed=completed + 1,
                            total=total,
                        )

                    completed += 1

                    yield CrawlEvent(
                        type="progress",
                        completed=completed,
                        total=total,
                    )

                # Final complete event
                yield CrawlEvent(
                    type="complete",
                    completed=completed,
                    total=total,
                )

                # Finalize output adapter
                if output_adapter:
                    await output_adapter.complete()

        except Exception as e:
            LOGGER.error(f"Crawl failed: {e}", exc_info=True)
            if output_adapter:
                await output_adapter.abort(str(e))
            yield CrawlEvent(
                type="error",
                error=str(e),
            )

    def _matches_patterns(self, url: str, patterns: list[str]) -> bool:
        """Check if URL matches any pattern.

        Args:
            url: URL to check
            patterns: Patterns to match against

        Returns:
            True if URL matches any pattern
        """
        import fnmatch

        return any(fnmatch.fnmatch(url, pattern) for pattern in patterns)

    def _load_resume_state(self, output_dir: Path) -> set[str]:
        """Load URLs that have already been scraped.

        Args:
            output_dir: Output directory

        Returns:
            Set of already-scraped URLs
        """
        scraped = set()
        manifest_path = output_dir / "manifest.json"

        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
                scraped = set(manifest.get("scraped_urls", []))

        return scraped

    def _save_page(self, output_dir: Path, url: str, data: ScrapeData) -> None:
        """Save scraped page to output directory.

        Args:
            output_dir: Output directory
            url: Source URL
            data: ScrapeData to save
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate base filename from URL
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_") or "index"

        # Check for duplicates and add hash suffix if needed
        base_path = path
        if (output_dir / f"{path}.md").exists() or (output_dir / f"{path}.html").exists():
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
            base_path = f"{path}_{url_hash}"

        # Save requested formats
        formats = getattr(self, "_formats", ["markdown"])

        if "markdown" in formats and data.markdown:
            with open(output_dir / f"{base_path}.md", "w") as f:
                # Add frontmatter
                f.write("---\n")
                f.write(f"source_url: {url}\n")
                if data.metadata and data.metadata.title:
                    f.write(f"title: {data.metadata.title}\n")
                f.write("---\n\n")
                f.write(data.markdown)

        if "html" in formats and data.html:
            with open(output_dir / f"{base_path}.html", "w") as f:
                f.write(data.html)

        if "json" in formats:
            with open(output_dir / f"{base_path}.json", "w") as f:
                json.dump(
                    {
                        "url": url,
                        "markdown": data.markdown,
                        "html": data.html,
                        "metadata": {
                            "title": data.metadata.title if data.metadata else None,
                            "description": data.metadata.description if data.metadata else None,
                            "source_url": data.metadata.source_url if data.metadata else url,
                        },
                    },
                    f,
                    indent=2,
                )

        # Update manifest
        manifest_path = output_dir / "manifest.json"
        manifest = {"scraped_urls": []}
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)

        if "scraped_urls" not in manifest:
            manifest["scraped_urls"] = []

        manifest["scraped_urls"].append(url)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
