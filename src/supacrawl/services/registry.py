"""Shared services registry: the single ``SupacrawlServices`` wrapper both the
REST API and the MCP layer inject into their tool/route handlers.

This module is deliberately free of any fastmcp/mcp-common/pydantic-settings
dependency so an api-only install (``supacrawl[api]``, no ``mcp`` extra) can
import and construct it. The MCP layer's FastMCP-specific wiring lives in
``supacrawl.mcp``.

NOTE: Agent tools are intentionally omitted from this MCP server. When using
supacrawl via MCP, the controlling LLM (Claude, ChatGPT, etc.) IS the agent -
it orchestrates the primitives. See README for rationale.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supacrawl.services import (
        BrowserManager,
        CrawlService,
        MapService,
        ScrapeService,
        SearchService,
    )

logger = logging.getLogger(__name__)


class SupacrawlServices:
    """
    MCP wrapper providing unified access to all supacrawl services.

    This wrapper provides:
    1. Unified access to all services via a single object
    2. Connection testing for MCP health checks
    3. Cleanup/lifecycle management
    4. Service status for health reporting

    All services are created externally and passed in during initialization.
    """

    def __init__(
        self,
        browser_manager: "BrowserManager",
        scrape_service: "ScrapeService",
        crawl_service: "CrawlService",
        map_service: "MapService",
        search_service: "SearchService",
    ):
        """
        Initialise services wrapper.

        Args:
            browser_manager: Browser lifecycle manager
            scrape_service: Single URL scraping service
            crawl_service: Website crawling service
            map_service: URL mapping/discovery service
            search_service: Web search service
        """
        self.browser_manager = browser_manager
        self.scrape_service = scrape_service
        self.crawl_service = crawl_service
        self.map_service = map_service
        self.search_service = search_service

        logger.info("Supacrawl services wrapper initialised")

    async def test_connection(self) -> bool:
        """
        Test connection for MCP health checks.

        Verifies that the browser is running and core services are available.

        Returns:
            True if connection successful

        Raises:
            Exception: If connection test fails
        """
        try:
            # Verify browser is running
            if not self.browser_manager:
                raise RuntimeError("Browser manager not initialised")

            # All services should be non-None
            services_ok = all(
                [
                    self.scrape_service is not None,
                    self.crawl_service is not None,
                    self.map_service is not None,
                    self.search_service is not None,
                ]
            )

            if not services_ok:
                raise RuntimeError("One or more services not initialised")

            logger.info("Connection test successful")
            return True

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            raise

    def get_service_status(self) -> dict[str, bool]:
        """
        Get status of all services for health reporting.

        Returns:
            Dict mapping service names to availability status
        """
        return {
            "browser": self.browser_manager is not None,
            "scrape": self.scrape_service is not None,
            "crawl": self.crawl_service is not None,
            "map": self.map_service is not None,
            "search": self.search_service is not None,
        }

    async def close(self) -> None:
        """Close and cleanup all services."""
        if self.search_service:
            await self.search_service.close()

        if self.browser_manager:
            await self.browser_manager.stop()

        logger.info("Supacrawl services closed")


async def create_supacrawl_services() -> SupacrawlServices:
    """
    Factory function to create and initialise all supacrawl services.

    Returns:
        Initialised SupacrawlServices wrapper

    Raises:
        Exception: If service creation fails
    """
    from pathlib import Path

    from supacrawl.config import SupacrawlSecrets, load_config
    from supacrawl.models import LocaleConfig

    config = load_config()
    secrets = SupacrawlSecrets.from_env()

    # Get locale config from settings
    locale_config = LocaleConfig(language=config.locale, timezone=config.timezone)

    from supacrawl.services import (
        BrowserManager,
        CrawlService,
        MapService,
        ScrapeService,
        SearchService,
    )

    # Create shared browser manager with config
    browser_manager = BrowserManager(
        headless=config.headless,
        timeout_ms=config.timeout,
        user_agent=config.user_agent,
        locale_config=locale_config,
        stealth=config.stealth,
        proxy=secrets.proxy,
        engine=config.engine,
    )

    # Initialise browser
    await browser_manager.start()

    # Log enabled features
    features = []
    if config.engine:
        features.append(f"engine:{config.engine}")
    if config.stealth:
        features.append("stealth")
    if secrets.proxy:
        features.append("proxy")
    if config.cache_dir:
        features.append("caching")
    if config.solve_captcha:
        features.append("captcha-solving")
    if config.locale != "en-US" or config.timezone != "UTC":
        features.append(f"locale:{config.locale}/{config.timezone}")
    if features:
        logger.info(f"Enabled features: {', '.join(features)}")

    # Create supacrawl library services. Per-domain strategy memory (#130) is on
    # by default for the MCP server — the primary entry point — so repeated hits
    # to a domain are seeded with the strategy that last worked. Disable with
    # SUPACRAWL_STRATEGY_MEMORY=0.
    # Field telemetry (#137) is likewise on by default for the MCP server so
    # scrape/search quality and usage are tracked over time. Disable with
    # SUPACRAWL_METRICS=0.
    from supacrawl.services.strategy_memory import StrategyStore
    from supacrawl.telemetry import MetricsSink

    telemetry = MetricsSink.default()
    cache_dir = Path(config.cache_dir).expanduser() if config.cache_dir else None

    scrape_service = ScrapeService(
        browser=browser_manager,
        locale_config=locale_config,
        cache_dir=cache_dir,
        stealth=config.stealth,
        proxy=secrets.proxy,
        solve_captcha=config.solve_captcha,
        headless=config.headless,
        engine=config.engine,
        strategy_store=StrategyStore.default(),
        telemetry=telemetry,
    )
    map_service = MapService(browser=browser_manager)
    crawl_service = CrawlService(
        browser=browser_manager,
        map_service=map_service,
        scrape_service=scrape_service,
    )

    # Create search service from supacrawl library
    # Prefer multi-provider chain (search_providers) over legacy single provider
    search_service = SearchService(
        scrape_service=scrape_service,
        providers=config.search_providers,
        provider=config.search_provider if not config.search_providers else None,
        brave_api_key=secrets.brave_api_key,
        rate_limit=config.search_rate_limit,
        locale_config=locale_config,
        telemetry=telemetry,
    )

    logger.info("Supacrawl services initialised")

    return SupacrawlServices(
        browser_manager=browser_manager,
        scrape_service=scrape_service,
        crawl_service=crawl_service,
        map_service=map_service,
        search_service=search_service,
    )
