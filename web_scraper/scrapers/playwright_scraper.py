"""Playwright-based scraper for web content extraction.

This module provides the core scraping mechanism using Playwright for
browser automation. It handles SPA sites with client-side routing.

Features:
1. Fresh browser context per crawl session
2. Waits for network idle and DOM stability before capturing
3. Handles JavaScript-rendered content
4. Configurable politeness settings (delays, concurrency)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.async_api import async_playwright, Browser, Page as PlaywrightPage

from web_scraper.content import normalise_url, postprocess_markdown
from web_scraper.exceptions import ProviderError, generate_correlation_id
from web_scraper.models import Page, SiteConfig
from web_scraper.utils import content_hash, log_with_correlation, url_path

if TYPE_CHECKING:
    from web_scraper.corpus.writer import IncrementalSnapshotWriter

LOGGER = logging.getLogger(__name__)


def _local_content_hash(content: str) -> str:
    """Generate SHA-256 hash of content for deduplication (local helper)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


async def _wait_for_spa_content(
    page: PlaywrightPage,
    url: str,
    timeout_ms: int = 10000,
) -> None:
    """Wait for SPA content to stabilize after navigation.

    This function waits for:
    1. Network to be idle (no pending requests)
    2. At least one heading element to exist
    3. DOM content to stabilize (no changes for 500ms)

    Args:
        page: Playwright page instance.
        url: URL being navigated to (for logging).
        timeout_ms: Maximum wait time in milliseconds.
    """
    start_time = asyncio.get_event_loop().time()
    max_wait = timeout_ms / 1000

    # Wait for at least one heading to appear
    try:
        await page.wait_for_selector("h1, h2, main, article", timeout=timeout_ms)
    except Exception:
        # If no heading found, continue anyway
        pass

    # Wait for content stability (DOM not changing)
    last_content_hash = ""
    stable_count = 0
    required_stable = 3  # Need 3 consecutive stable checks (600ms total)

    while asyncio.get_event_loop().time() - start_time < max_wait:
        try:
            # Get current page content hash
            content = await page.content()
            current_hash = _local_content_hash(content)

            if current_hash == last_content_hash:
                stable_count += 1
                if stable_count >= required_stable:
                    LOGGER.debug(
                        f"SPA content stable after {stable_count} checks for {url}"
                    )
                    return
            else:
                stable_count = 0
                last_content_hash = current_hash

            await asyncio.sleep(0.2)  # Check every 200ms
        except Exception as e:
            LOGGER.warning(f"Error checking content stability for {url}: {e}")
            break

    LOGGER.debug(f"SPA content wait timed out for {url}, proceeding anyway")


async def _scrape_url_with_playwright(
    browser: Browser,
    url: str,
    config: SiteConfig,
    correlation_id: str,
) -> Page | None:
    """Scrape a single URL using Playwright directly.

    Args:
        browser: Playwright browser instance.
        url: URL to scrape.
        config: Site configuration.
        correlation_id: Correlation ID for logging.

    Returns:
        Page object or None if scraping failed.
    """
    context = None
    page = None

    try:
        # Create fresh browser context for isolation
        context = await browser.new_context(
            locale=os.getenv("WEB_SCRAPER_LOCALE", "en-US"),
            timezone_id=os.getenv("WEB_SCRAPER_TIMEZONE", "Australia/Brisbane"),
            user_agent=os.getenv(
                "WEB_SCRAPER_USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            ),
        )

        page = await context.new_page()

        # Navigate to URL
        page_timeout = int(config.politeness.page_timeout * 1000)
        wait_until = os.getenv("WEB_SCRAPER_WAIT_UNTIL", "domcontentloaded")

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            "Playwright navigating to URL",
            correlation_id=correlation_id,
            url=url,
            wait_until=wait_until,
        )

        await page.goto(url, wait_until=wait_until, timeout=page_timeout)

        # Wait for SPA content to stabilize
        spa_delay = float(os.getenv("WEB_SCRAPER_SPA_DELAY", "2.0"))
        await _wait_for_spa_content(page, url, timeout_ms=int(spa_delay * 1000))

        # Additional fixed delay for any remaining JS execution
        await asyncio.sleep(0.5)

        # Extract HTML content
        html = await page.content()

        if not html or len(html.strip()) < 100:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                "Playwright got empty or minimal content",
                correlation_id=correlation_id,
                url=url,
                html_length=len(html) if html else 0,
            )
            return None

        # Extract title
        browser_title = await page.title() or ""

        # Convert HTML to markdown using markdownify
        raw_markdown = _html_to_markdown(html, config)

        if not raw_markdown or not raw_markdown.strip():
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                "Playwright got empty markdown after conversion",
                correlation_id=correlation_id,
                url=url,
            )
            return None

        # Normalise URL
        normalised_url = normalise_url(url, html=html, entrypoint=url)

        # Apply markdown post-processing pipeline (sanitize, language detection)
        result = postprocess_markdown(raw_markdown)
        markdown = result.markdown
        lang_info = result.language

        # Get title from browser or first heading in markdown
        title = browser_title
        if not title:
            for line in markdown.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    title = stripped[2:].strip()
                    break
            if not title:
                title = "Untitled"

        # Build extra metadata
        extra = {
            "language": lang_info.get("language", "unknown"),
            "language_confidence": lang_info.get("confidence", 0.0),
            "language_action": lang_info.get("action", "none"),
        }

        # Build Page object with correct fields
        assert config.id is not None, "config.id must be set after validation"
        page_obj = Page(
            site_id=config.id,
            url=normalised_url,
            title=title,
            path=url_path(normalised_url),
            content_markdown=markdown,
            content_html=html if "html" in config.formats else None,
            content_hash=content_hash(markdown),
            provider="playwright",
            extra=extra,
        )

        log_with_correlation(
            LOGGER,
            logging.INFO,
            "Playwright scraped page successfully",
            correlation_id=correlation_id,
            url=normalised_url,
            html_lines=len(html.splitlines()),
            markdown_lines=len(markdown.splitlines()) if markdown else 0,
        )

        return page_obj

    except Exception as e:
        log_with_correlation(
            LOGGER,
            logging.ERROR,
            f"Playwright failed to scrape URL: {e}",
            correlation_id=correlation_id,
            url=url,
            error=str(e),
        )
        return None

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


def _html_to_markdown(
    html: str,
    config: SiteConfig,
) -> str:
    """Convert HTML to markdown using markdownify.

    Uses BeautifulSoup to extract main content and markdownify for conversion.
    This produces Firecrawl-compatible markdown output.

    Args:
        html: Raw HTML content.
        config: Site configuration.

    Returns:
        Markdown string.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, nav, footer, header elements
        for tag in soup.find_all(
            ["script", "style", "nav", "footer", "header", "noscript"]
        ):
            tag.decompose()

        # Get main content area if only_main_content is set
        content_element = None
        if config.only_main_content:
            # Try various main content selectors
            for selector in [
                "main",
                "article",
                "[role='main']",
                ".content",
                "#content",
                ".main-content",
            ]:
                content_element = soup.select_one(selector)
                if content_element:
                    break

        # Use main content or fall back to body
        if content_element:
            html_to_convert = str(content_element)
        else:
            body = soup.find("body")
            html_to_convert = str(body) if body else str(soup)

        # Convert to markdown using markdownify
        # Options match Firecrawl-style output
        markdown = md(
            html_to_convert,
            heading_style="atx",  # Use # style headings
            bullets="-",  # Use - for unordered lists
            code_language="",  # Don't assume language for code blocks
            strip=["script", "style", "nav", "footer", "header"],
            wrap=False,  # Don't wrap lines
            wrap_width=0,  # No line width limit
        )

        # Clean up excessive whitespace
        lines = []
        prev_empty = False
        for line in markdown.splitlines():
            stripped = line.rstrip()
            is_empty = not stripped

            # Collapse multiple empty lines to at most 2
            if is_empty:
                if not prev_empty:
                    lines.append("")
                prev_empty = True
            else:
                lines.append(stripped)
                prev_empty = False

        return "\n".join(lines).strip()

    except Exception as e:
        LOGGER.warning(f"Markdown conversion failed: {e}")
        # Fallback: extract text from HTML
        try:
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(separator="\n\n", strip=True)
        except Exception:
            return ""


class PlaywrightScraper:
    """Playwright-based scraper for web content extraction.

    Uses Playwright for browser automation to handle JavaScript-rendered
    content including SPAs with client-side routing.

    Usage:
        scraper = PlaywrightScraper()
        pages, snapshot_path = scraper.crawl(config, target_urls=url_list)
    """

    provider_name = "playwright"

    def __init__(self) -> None:
        """Initialize the Playwright scraper."""
        pass

    def crawl(
        self,
        config: SiteConfig,
        corpora_dir: Path | None = None,
        resume_snapshot: Path | None = None,
        target_urls: list[str] | None = None,
    ) -> tuple[list[Page], Path]:
        """Crawl using direct Playwright.

        Args:
            config: Site configuration to crawl.
            corpora_dir: Base corpora directory.
            resume_snapshot: Path to snapshot to resume from (not supported).
            target_urls: Explicit list of URLs to crawl (required).

        Returns:
            Tuple of scraped Page objects and snapshot path.

        Raises:
            ProviderError: On errors.
            ValueError: If target_urls is not provided.
        """
        if not target_urls:
            msg = "PlaywrightScraper requires explicit target_urls list"
            raise ValueError(msg)

        correlation_id = generate_correlation_id()

        # Import here to avoid circular imports
        from web_scraper.corpus.writer import IncrementalSnapshotWriter

        snapshot_writer = IncrementalSnapshotWriter(
            config,
            corpora_dir or (Path.cwd() / "corpora"),
            resume_snapshot=resume_snapshot,
        )
        snapshot_writer.crawl_settings = {
            "provider": "playwright",
            "locale": os.getenv("WEB_SCRAPER_LOCALE", "en-US"),
            "timezone": os.getenv("WEB_SCRAPER_TIMEZONE", "Australia/Brisbane"),
            "wait_until": os.getenv("WEB_SCRAPER_WAIT_UNTIL", "domcontentloaded"),
            "spa_extra_delay": os.getenv("WEB_SCRAPER_SPA_DELAY", "2.0"),
        }

        try:
            pages = asyncio.run(
                self._crawl_async(config, correlation_id, snapshot_writer, target_urls)
            )
            asyncio.run(snapshot_writer.complete())
        except ProviderError:
            asyncio.run(snapshot_writer.abort("provider_error"))
            raise
        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.ERROR,
                f"Playwright crawl failed: {exc}",
                correlation_id=correlation_id,
                provider=self.provider_name,
                error=str(exc),
            )
            asyncio.run(snapshot_writer.abort(str(exc)))
            raise ProviderError(
                "Playwright crawl failed.",
                provider=self.provider_name,
                correlation_id=correlation_id,
                context={"error": str(exc)},
            ) from exc

        snapshot_path = snapshot_writer.snapshot_root()
        log_with_correlation(
            LOGGER,
            logging.INFO,
            f"Playwright returned {len(pages)} pages for site {config.id}",
            correlation_id=correlation_id,
            page_count=len(pages),
            site_id=config.id,
            provider=self.provider_name,
            snapshot=str(snapshot_path),
        )
        return snapshot_writer.get_pages(), snapshot_path

    async def _crawl_async(
        self,
        config: SiteConfig,
        correlation_id: str,
        writer: IncrementalSnapshotWriter,
        target_urls: list[str],
    ) -> list[Page]:
        """Asynchronously crawl URLs using Playwright.

        Args:
            config: Site configuration.
            correlation_id: Correlation ID for logging.
            writer: Snapshot writer.
            target_urls: URLs to crawl.

        Returns:
            List of Page objects.
        """
        pages: list[Page] = []
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()

        # Apply max_pages limit
        urls_to_crawl = target_urls[: config.max_pages]

        # Get delay settings
        delay_min, delay_max = config.politeness.delay_between_requests

        log_with_correlation(
            LOGGER,
            logging.INFO,
            "Starting Playwright crawl",
            correlation_id=correlation_id,
            url_count=len(urls_to_crawl),
            max_pages=config.max_pages,
            delay_range=(delay_min, delay_max),
            provider=self.provider_name,
        )

        await writer.start()

        headless = os.getenv("WEB_SCRAPER_HEADLESS", "true").lower() == "true"

        async with async_playwright() as p:
            # Launch browser once, create fresh contexts per URL
            browser = await p.chromium.launch(headless=headless)
            total = len(urls_to_crawl)

            try:
                for i, url in enumerate(urls_to_crawl):
                    # Check max_pages limit
                    if len(pages) >= config.max_pages:
                        break

                    # Skip if already seen
                    if url in seen_urls:
                        continue

                    # Show progress
                    completed = len(pages)
                    if total > 0:
                        pct = int((completed / total) * 100)
                        bar_width = 25
                        filled = int(bar_width * completed / total) if total > 0 else 0
                        bar = "=" * filled + ">" + " " * (bar_width - filled - 1)
                        # Use print with flush for immediate output
                        print(
                            f"\r[{bar}] {completed}/{total} pages ({pct}%)",
                            end="",
                            flush=True,
                        )

                    # Scrape URL
                    page_obj = await _scrape_url_with_playwright(
                        browser, url, config, correlation_id
                    )

                    if page_obj:
                        # Check for duplicate content using content_hash
                        page_content_hash = page_obj.content_hash
                        if page_content_hash and page_content_hash in seen_hashes:
                            log_with_correlation(
                                LOGGER,
                                logging.WARNING,
                                "Duplicate content detected, skipping",
                                correlation_id=correlation_id,
                                url=url,
                                content_hash=page_content_hash,
                                provider=self.provider_name,
                            )
                            continue

                        seen_urls.add(url)
                        if page_content_hash:
                            seen_hashes.add(page_content_hash)

                        pages.append(page_obj)
                        await writer.add_pages([page_obj])

                        # Show page scraped
                        from urllib.parse import urlparse
                        path = urlparse(url).path or "/"
                        print(f"\n  + {path}", flush=True)

                    # Delay between requests (except for last URL)
                    if i < len(urls_to_crawl) - 1:
                        delay = delay_min + random.random() * (delay_max - delay_min)
                        await asyncio.sleep(delay)

                # Final progress update
                print(
                    f"\r[{'=' * 25}>] {len(pages)}/{total} pages (100%)",
                    flush=True,
                )

            finally:
                await browser.close()

        # Log duplicate detection summary
        unique_count = len(seen_hashes)
        total_count = len(pages)
        if unique_count < total_count:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Content deduplication: {total_count} pages, {unique_count} unique",
                correlation_id=correlation_id,
                provider=self.provider_name,
            )

        return pages
