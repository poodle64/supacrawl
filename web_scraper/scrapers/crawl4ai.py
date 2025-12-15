"""Crawl4AI provider implementation using the Crawl4AI SDK with optional LLM integration."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from pathlib import Path
from typing import Any

try:
    # Python 3.12+
    from typing import override
except ImportError:
    from typing_extensions import override

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, LLMExtractionStrategy  # type: ignore[import-untyped]
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter  # type: ignore[import-untyped]

from web_scraper.content.cleaner import clean_markdown
from web_scraper.exceptions import ProviderError, generate_correlation_id
from web_scraper.models import Page, SiteConfig
from web_scraper.scrapers.base import Scraper
from web_scraper.scrapers.crawl4ai_config import (
    build_browser_config,
    build_llm_config,
    build_markdown_generator,
    cache_mode,
)
from web_scraper.scrapers.crawl4ai_deep import build_deep_crawl_strategy
from web_scraper.scrapers.crawl4ai_result import extract_pages_from_result
from web_scraper.scrapers.crawl4ai_retry import (
    is_client_error,
    retry_attempts,
    retry_backoff,
    retry_base_delay,
    retry_jitter,
)
from web_scraper.utils import log_with_correlation
from web_scraper.corpus.writer import IncrementalSnapshotWriter
from web_scraper.corpus.state import CrawlState, load_state
from web_scraper.rate_limit import RateLimiter
from web_scraper.browser.pool import BrowserPool
from web_scraper.network.proxy import ProxyRotator

LOGGER = logging.getLogger(__name__)


class Crawl4AIScraper(Scraper):
    """Crawl4AI provider backed by the local SDK."""

    provider_name = "crawl4ai"

    def __init__(
        self,
        crawler: AsyncWebCrawler | None = None,
        rate_limiter: RateLimiter | None = None,
        browser_pool: BrowserPool | None = None,
        proxy_rotator: ProxyRotator | None = None,
    ) -> None:
        """
        Initialise the Crawl4AI provider.

        Args:
            crawler: Optional preconfigured AsyncWebCrawler (useful for testing).
            rate_limiter: Optional rate limiter for politeness controls.
            browser_pool: Optional browser pool for efficient browser reuse.
            proxy_rotator: Optional proxy rotator for proxy rotation.
        """
        self._crawler = crawler
        self._rate_limiter = rate_limiter
        self._browser_pool = browser_pool
        self._proxy_rotator = proxy_rotator

    @override
    def crawl(
        self,
        config: SiteConfig,
        corpora_dir: Path | None = None,
        resume_snapshot: Path | None = None,
        target_urls: list[str] | None = None,
    ) -> tuple[list[Page], Path]:
        """
        Crawl using Crawl4AI SDK.

        Args:
            config: Site configuration to crawl.
            corpora_dir: Base corpora directory (defaults to cwd/corpora if None).
            resume_snapshot: Path to snapshot to resume from.
            target_urls: Optional explicit list of URLs to crawl.
                If provided, only crawl these URLs (no link discovery).

        Returns:
            Tuple of scraped Page objects and snapshot path.

        Raises:
            ProviderError: On SDK errors or unexpected response structures.
        """
        correlation_id = generate_correlation_id()

        # Load state if resuming
        state: CrawlState | None = None
        if resume_snapshot:
            state = load_state(resume_snapshot)

        snapshot_writer = IncrementalSnapshotWriter(
            config,
            corpora_dir or (Path.cwd() / "corpora"),
            resume_snapshot=resume_snapshot,
        )
        snapshot_writer.crawl_settings = _crawl_settings_summary()
        try:
            # Bridge async SDK to sync interface using asyncio.run()
            pages = asyncio.run(
                self._crawl_async(config, correlation_id, snapshot_writer, state, target_urls)
            )
            asyncio.run(snapshot_writer.complete())
        except ProviderError:
            asyncio.run(snapshot_writer.abort("provider_error"))
            raise
        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.ERROR,
                f"Crawl4AI crawl failed unexpectedly: {exc}",
                correlation_id=correlation_id,
                provider=self.provider_name,
                error=str(exc),
                error_type=str(type(exc)),
            )
            msg = "Crawl4AI crawl failed unexpectedly."
            asyncio.run(snapshot_writer.abort(str(exc)))
            raise ProviderError(
                msg,
                provider=self.provider_name,
                correlation_id=correlation_id,
                context={"error": str(exc), "error_type": str(type(exc))},
            ) from exc

        snapshot_path = snapshot_writer.snapshot_root()
        log_with_correlation(
            LOGGER,
            logging.INFO,
            f"Crawl4AI returned {len(pages)} pages for site {config.id}",
            correlation_id=correlation_id,
            page_count=len(pages),
            site_id=config.id,
            provider=self.provider_name,
            snapshot=str(snapshot_path),
        )
        return snapshot_writer.get_filtered_pages(), snapshot_path

    async def _crawl_async(
        self,
        config: SiteConfig,
        correlation_id: str,
        writer: IncrementalSnapshotWriter,
        state: CrawlState | None = None,
        target_urls: list[str] | None = None,
    ) -> list[Page]:
        """
        Asynchronously crawl using Crawl4AI SDK.

        Args:
            config: Site configuration to crawl.
            correlation_id: Correlation ID for logging.
            writer: Snapshot writer for incremental saves.
            state: Optional crawl state for resumption.
            target_urls: Optional explicit list of URLs to crawl.
                If provided, only crawl these URLs (no link discovery).

        Returns:
            List of scraped Page objects.

        Raises:
            ProviderError: On SDK errors or unexpected response structures.
        """
        pages: list[Page] = []

        # Initialize state for tracking
        if state is None:
            state = CrawlState()
        seen_urls: set[str] = state.completed_urls.copy()

        # Use provided crawler or create a new one with best-practice browser config
        crawler = self._crawler or AsyncWebCrawler(config=build_browser_config())

        try:
            await writer.start()
            async with crawler:
                # If target_urls provided, crawl only those URLs (no discovery)
                if target_urls is not None:
                    # Apply max_pages limit
                    urls_to_crawl = target_urls[:config.max_pages]
                    
                    log_with_correlation(
                        LOGGER,
                        logging.INFO,
                        "Crawling explicit URL list (no discovery)",
                        correlation_id=correlation_id,
                        url_count=len(urls_to_crawl),
                        max_pages=config.max_pages,
                        provider=self.provider_name,
                    )
                    
                    for url in urls_to_crawl:
                        # Check if we've hit max_pages limit
                        if len(pages) >= config.max_pages:
                            break
                        
                        # Skip if already seen
                        if url in seen_urls:
                            continue
                        
                        try:
                            log_with_correlation(
                                LOGGER,
                                logging.INFO,
                                "Crawling target URL",
                                correlation_id=correlation_id,
                                url=url,
                                provider=self.provider_name,
                            )
                            # Crawl single URL without link discovery
                            new_pages = await self._crawl_entrypoint(
                                crawler, url, config, correlation_id, disable_deep_crawl=True
                            )
                            
                            # Deduplicate pages by URL
                            to_write: list[Page] = []
                            for page in new_pages:
                                normalised_url = page.url
                                if normalised_url in seen_urls:
                                    continue
                                
                                # Apply cleaning only for enhanced preset
                                if config.markdown_quality_preset == "enhanced":
                                    original_headings = [
                                        line
                                        for line in page.content_markdown.splitlines()
                                        if line.strip() and line.strip().startswith("#")
                                    ]
                                    clean_content = clean_markdown(
                                        page.content_markdown, config.cleaning
                                    )
                                else:
                                    clean_content = page.content_markdown
                                    original_headings = []
                                
                                # If cleaning removed all headings, restore them (enhanced preset only)
                                if config.markdown_quality_preset == "enhanced":
                                    cleaned_headings = [
                                        line
                                        for line in clean_content.splitlines()
                                        if line.strip() and line.strip().startswith("#")
                                    ]
                                    if not cleaned_headings and original_headings:
                                        max_restore = config.cleaning.skip_until_heading and 10 or 0
                                        if max_restore:
                                            headings_to_restore = original_headings[:max_restore]
                                            clean_content = (
                                                "\n".join(headings_to_restore) + "\n\n" + clean_content
                                            )
                                page = page.model_copy(update={"content_markdown": clean_content})
                                seen_urls.add(normalised_url)
                                pages.append(page)
                                to_write.append(page)
                            
                            if to_write:
                                await writer.add_pages(to_write)
                                
                        except ProviderError:
                            raise
                        except Exception as exc:
                            log_with_correlation(
                                LOGGER,
                                logging.ERROR,
                                f"Failed to crawl target URL {url}: {exc}",
                                correlation_id=correlation_id,
                                url=url,
                                provider=self.provider_name,
                                error=str(exc),
                            )
                            # Continue with next URL instead of failing entire crawl
                            continue
                    
                    return pages
                
                # Default behavior: crawl entrypoints with discovery
                # Crawl each entrypoint once
                crawled_entrypoints: set[str] = set()

                for entrypoint in config.entrypoints:
                        # Skip if already crawled
                        if entrypoint in crawled_entrypoints:
                            continue

                        # Check if we've hit max_pages limit
                        if len(pages) >= config.max_pages:
                            log_with_correlation(
                                LOGGER,
                                logging.INFO,
                                "Reached max_pages limit, stopping crawl",
                                correlation_id=correlation_id,
                                total_pages=len(pages),
                                max_pages=config.max_pages,
                                provider=self.provider_name,
                            )
                            break

                        try:
                            log_with_correlation(
                                LOGGER,
                                logging.INFO,
                                "Starting Crawl4AI entrypoint",
                                correlation_id=correlation_id,
                                entrypoint=entrypoint,
                                provider=self.provider_name,
                            )
                            new_pages = await self._crawl_entrypoint(
                                crawler, entrypoint, config, correlation_id
                            )
                            log_with_correlation(
                                LOGGER,
                                logging.INFO,
                                "Completed entrypoint",
                                correlation_id=correlation_id,
                                entrypoint=entrypoint,
                                provider=self.provider_name,
                                page_count=len(new_pages),
                            )
                            await writer.log_event(
                                {
                                    "type": "entrypoint_completed",
                                    "entrypoint": entrypoint,
                                    "page_count": len(new_pages),
                                }
                            )
                        except ProviderError:
                            raise
                        except Exception as exc:
                            log_with_correlation(
                                LOGGER,
                                logging.ERROR,
                                f"Crawl4AI entrypoint failed: {exc}",
                                correlation_id=correlation_id,
                                entrypoint=entrypoint,
                                provider=self.provider_name,
                                error=str(exc),
                                error_type=str(type(exc)),
                            )
                            raise ProviderError(
                                f"Failed to crawl entrypoint {entrypoint}.",
                                provider=self.provider_name,
                                correlation_id=correlation_id,
                                context={"entrypoint": entrypoint, "error": str(exc)},
                            ) from exc

                        # Deduplicate pages by URL
                        to_write: list[Page] = []
                        for page in new_pages:
                            normalised_url = page.url
                            if normalised_url in seen_urls:
                                continue
                            # Apply cleaning only for enhanced preset
                            if config.markdown_quality_preset == "enhanced":
                                # Preserve headings before cleaning
                                original_headings = [
                                    line
                                    for line in page.content_markdown.splitlines()
                                    if line.strip() and line.strip().startswith("#")
                                ]
                                # Use configurable cleaner with site-specific rules
                                clean_content = clean_markdown(
                                    page.content_markdown, config.cleaning
                                )
                            else:
                                # Pure Crawl4AI preset: skip cleaning
                                clean_content = page.content_markdown
                                original_headings = []
                            
                            # If cleaning removed all headings, restore them (enhanced preset only)
                            if config.markdown_quality_preset == "enhanced":
                                cleaned_headings = [
                                    line
                                    for line in clean_content.splitlines()
                                    if line.strip() and line.strip().startswith("#")
                                ]
                                if not cleaned_headings and original_headings:
                                    # Prepend original headings to cleaned content
                                    max_restore = config.cleaning.skip_until_heading and 10 or 0
                                    if max_restore:
                                        headings_to_restore = original_headings[:max_restore]
                                        clean_content = (
                                            "\n".join(headings_to_restore) + "\n\n" + clean_content
                                        )
                            page = page.model_copy(update={"content_markdown": clean_content})
                            seen_urls.add(normalised_url)
                            pages.append(page)
                            to_write.append(page)

                        if to_write:
                            await writer.add_pages(to_write)

                        # Mark entrypoint as crawled
                        crawled_entrypoints.add(entrypoint)

                        # Break if we've hit max_pages
                        if len(pages) >= config.max_pages:
                            break

        except Exception as exc:
            error_str = str(exc)
            error_type = type(exc).__name__

            # Check for Playwright browser installation issues
            is_playwright_error = (
                "playwright" in error_str.lower()
                or "Executable doesn't exist" in error_str
                or "BrowserType.launch" in error_str
            )

            if is_playwright_error:
                log_with_correlation(
                    LOGGER,
                    logging.ERROR,
                    "Crawl4AI failed: Playwright browsers not installed",
                    correlation_id=correlation_id,
                    provider=self.provider_name,
                    error=error_str,
                )
                msg = (
                    "Crawl4AI requires Playwright browsers to be installed. "
                    "Run 'playwright install' or 'crawl4ai-setup' to install browser dependencies. "
                    "See https://docs.crawl4ai.com/core/installation/ for details."
                )
            else:
                log_with_correlation(
                    LOGGER,
                    logging.ERROR,
                    f"Crawl4AI crawler context failed: {error_str}",
                    correlation_id=correlation_id,
                    provider=self.provider_name,
                    error=error_str,
                    error_type=error_type,
                )
                msg = "Crawl4AI crawler failed to initialise or cleanup."

            await writer.abort(error_str)
            raise ProviderError(
                msg,
                provider=self.provider_name,
                correlation_id=correlation_id,
                context={"error": error_str, "error_type": error_type},
            ) from exc

        return pages

    async def _crawl_entrypoint(
        self,
        crawler: AsyncWebCrawler,
        entrypoint: str,
        config: SiteConfig,
        correlation_id: str,
        disable_deep_crawl: bool = False,
    ) -> list[Page]:
        """
        Crawl a single entrypoint using Crawl4AI SDK.

        Args:
            crawler: AsyncWebCrawler instance.
            entrypoint: Entrypoint URL to crawl.
            config: Site configuration.
            correlation_id: Correlation ID for logging.
            disable_deep_crawl: If True, disable link discovery (single page only).

        Returns:
            List of scraped Page objects.

        Raises:
            ProviderError: On SDK errors or unexpected response structures.
        """
        # Build filter chain for include/exclude patterns
        filters: list[URLPatternFilter] = []
        if config.include:
            include_filter = URLPatternFilter(patterns=config.include)
            filters.append(include_filter)
        if config.exclude:
            exclude_filter = URLPatternFilter(patterns=config.exclude, reverse=True)
            filters.append(exclude_filter)
        filter_chain = FilterChain(filters) if filters else None

        # For single-page crawls or when deep crawl disabled, skip deep crawl
        deep_crawl_strategy = None
        if not disable_deep_crawl and config.max_pages > 1:
            deep_crawl_strategy = build_deep_crawl_strategy(config, filter_chain)

        # Build LLM configuration (generic provider or Ollama fallback)
        llm_config = build_llm_config(correlation_id)
        extraction_strategy = None
        if llm_config:
            extraction_strategy = LLMExtractionStrategy(llm_config=llm_config)
            log_with_correlation(
                LOGGER,
                logging.INFO,
                "Using LLM provider for content extraction",
                correlation_id=correlation_id,
                provider=self.provider_name,
                llm_provider=llm_config.provider,
            )

        # Build markdown generator with content filters and optional LLM content filter
        markdown_generator = build_markdown_generator(llm_config, correlation_id, config)

        # Build crawler run configuration (Crawl4AI 0.7.8+)
        run_config = CrawlerRunConfig(
            deep_crawl_strategy=deep_crawl_strategy,
            cache_mode=cache_mode(),
            word_count_threshold=10,
            process_iframes=True,
            stream=False,  # Return list of results (default)
            magic=True,  # Enable magic mode for better content extraction
            scan_full_page=True,
            scroll_delay=0.2,
            wait_until=os.getenv("CRAWL4AI_WAIT_UNTIL", "networkidle"),
            wait_for_images=config.only_main_content,  # Wait for images when extracting main content
            delay_before_return_html=0.25,
            page_timeout=120000,
            markdown_generator=markdown_generator,
            extraction_strategy=extraction_strategy,  # Use LLM if configured
            locale=os.getenv("CRAWL4AI_LOCALE", "en-US"),
            timezone_id=os.getenv("CRAWL4AI_TIMEZONE", "America/New_York"),
            js_code=_navigator_overrides_js(),
        )
        # Optionally attach request blocking patterns if the SDK supports it
        blocked = _blocked_resource_patterns()
        if hasattr(run_config, "blocked_resource_patterns"):
            run_config.blocked_resource_patterns = blocked

        entrypoint_timeout_ms = int(os.getenv("CRAWL4AI_ENTRYPOINT_TIMEOUT_MS", "180000"))

        attempts = retry_attempts()
        base_delay = retry_base_delay()
        backoff = retry_backoff()
        jitter = retry_jitter()
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                log_with_correlation(
                    LOGGER,
                    logging.INFO,
                    "Starting crawl attempt",
                    correlation_id=correlation_id,
                    entrypoint=entrypoint,
                    provider=self.provider_name,
                    attempt=attempt,
                    attempts=attempts,
                )
                result = await asyncio.wait_for(
                    crawler.arun(
                        url=entrypoint,
                        config=run_config,
                    ),
                    timeout=entrypoint_timeout_ms / 1000,
                )
                return extract_pages_from_result(
                    result,
                    entrypoint,
                    config,
                    self.provider_name,
                )
            except Exception as exc:
                last_error = exc
                retryable = not is_client_error(exc)
                log_level = logging.ERROR if (attempt == attempts or not retryable) else logging.WARNING
                log_with_correlation(
                    LOGGER,
                    log_level,
                    "Crawl4AI attempt failed",
                    correlation_id=correlation_id,
                    entrypoint=entrypoint,
                    provider=self.provider_name,
                    attempt=attempt,
                    attempts=attempts,
                    error=str(exc),
                    error_type=str(type(exc)),
                )
                if not retryable or attempt == attempts:
                    raise ProviderError(
                        f"Crawl4AI SDK crawl failed for {entrypoint}.",
                        provider=self.provider_name,
                        correlation_id=correlation_id,
                        context={
                            "entrypoint": entrypoint,
                            "attempt": attempt,
                            "attempts": attempts,
                            "error": str(exc),
                            "error_type": str(type(exc)),
                        },
                    ) from exc

                sleep_for = base_delay * (backoff ** (attempt - 1))
                sleep_for *= 1 + (jitter * random.random())
                await asyncio.sleep(sleep_for)

        # Should be unreachable, but keep a guard
        if last_error:
            raise ProviderError(
                f"Crawl4AI SDK crawl failed for {entrypoint}.",
                provider=self.provider_name,
                correlation_id=correlation_id,
                context={
                    "entrypoint": entrypoint,
                    "attempts": attempts,
                    "error": str(last_error),
                },
            ) from last_error

        return []


def _navigator_overrides_js() -> str:
    """
    Return JS snippet to enforce locale/timezone and navigator language hints.
    """
    locale = os.getenv("CRAWL4AI_LOCALE", "en-US")
    timezone = os.getenv("CRAWL4AI_TIMEZONE", "Australia/Brisbane")
    return f"""
    (() => {{
      const locale = "{locale}";
      const tz = "{timezone}";
      const langs = [locale, "en"];
      Object.defineProperty(navigator, "language", {{ get: () => locale }});
      Object.defineProperty(navigator, "languages", {{ get: () => langs }});
      const orig = Intl.DateTimeFormat.prototype.resolvedOptions;
      Intl.DateTimeFormat.prototype.resolvedOptions = function(...args) {{
        const opts = orig.apply(this, args);
        opts.locale = locale;
        opts.timeZone = tz;
        return opts;
      }};
      // Attempt to expand hidden sections
      setTimeout(() => {{
        const selectors = [
          "details summary",
          "button[aria-expanded]",
          "button",
          "[data-testid*=expand]",
          "[data-action*=expand]",
        ];
        const keywords = ["expand", "more", "show", "open"];
        let clicks = 0;
        const maxClicks = 8;
        selectors.forEach(sel => {{
          document.querySelectorAll(sel).forEach(el => {{
            if (clicks >= maxClicks) return;
            const text = (el.innerText || "").toLowerCase();
            if (keywords.some(k => text.includes(k))) {{
              try {{ el.click(); clicks += 1; }} catch (e) {{}}
            }}
          }});
        }});
        window.scrollTo({{ top: document.body.scrollHeight, behavior: "smooth" }});
      }}, 500);
    }})();
    """


def _blocked_resource_patterns() -> list[str]:
    """Common tracker/analytics patterns to block."""
    return [
        "doubleclick.net",
        "googletagmanager.com",
        "google-analytics.com",
        "analytics.twitter.com",
        "facebook.com/tr",
        "pixel",
        "scontent.fb",
        "adsystem",
    ]


def _crawl_settings_summary() -> dict[str, Any]:
    """Summarise crawl settings for manifest/run log."""
    return {
        "locale": os.getenv("CRAWL4AI_LOCALE", "en-US"),
        "timezone": os.getenv("CRAWL4AI_TIMEZONE", "Australia/Brisbane"),
        "accept_language": os.getenv("CRAWL4AI_ACCEPT_LANGUAGE", "en-US,en;q=0.8"),
        "user_agent": os.getenv(
            "CRAWL4AI_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        ),
        "headless": os.getenv("CRAWL4AI_HEADLESS", "true"),
        "proxy": os.getenv("CRAWL4AI_PROXY"),
        "wait_until": os.getenv("CRAWL4AI_WAIT_UNTIL", "networkidle"),
        "entrypoint_timeout_ms": os.getenv("CRAWL4AI_ENTRYPOINT_TIMEOUT_MS", "180000"),
    }


# NOTE: Site-specific _clean_page_markdown has been removed.
# Content cleaning is now handled by web_scraper.content.cleaner.clean_markdown
# using configurable CleaningConfig from SiteConfig.cleaning.
