"""MCP API client wrapper for Supacrawl.

Provides a unified interface to all supacrawl services for MCP tool injection.

NOTE: Agent tools are intentionally omitted from this MCP server. When using
supacrawl via MCP, the controlling LLM (Claude, ChatGPT, etc.) IS the agent -
it orchestrates the primitives. See README for rationale.
"""

from typing import TYPE_CHECKING

from supacrawl.mcp.config import logger, settings

if TYPE_CHECKING:
    from supacrawl.services import (
        BrowserManager,
        CrawlService,
        MapService,
        ScrapeService,
        SearchService,
    )


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
    import os

    from supacrawl.services import (
        BrowserManager,
        CrawlService,
        MapService,
        ScrapeService,
        SearchService,
    )

    # Get optional locale config from settings
    locale_config = settings.get_locale_config()

    # Create shared browser manager with config
    browser_manager = BrowserManager(
        headless=settings.headless,
        timeout_ms=settings.timeout,
        user_agent=settings.user_agent,
        locale_config=locale_config,
        stealth=settings.stealth,
        proxy=settings.proxy,
    )

    # Initialise browser
    await browser_manager.start()

    # Log enabled features
    features = []
    if settings.stealth:
        features.append("stealth")
    if settings.proxy:
        features.append("proxy")
    if settings.cache_dir:
        features.append("caching")
    if settings.solve_captcha:
        features.append("captcha-solving")
    if settings.locale != "en-US" or settings.timezone != "UTC":
        features.append(f"locale:{settings.locale}/{settings.timezone}")
    if features:
        logger.info(f"Enabled features: {', '.join(features)}")

    # Create supacrawl library services
    scrape_service = ScrapeService(
        browser=browser_manager,
        locale_config=locale_config,
        cache_dir=settings.get_cache_path(),
        stealth=settings.stealth,
        proxy=settings.proxy,
        solve_captcha=settings.solve_captcha,
    )
    map_service = MapService(browser=browser_manager)
    crawl_service = CrawlService(
        browser=browser_manager,
        map_service=map_service,
        scrape_service=scrape_service,
    )

    # Create search service from supacrawl library
    search_service = SearchService(
        scrape_service=scrape_service,
        provider=settings.search_provider,
        brave_api_key=os.getenv("BRAVE_API_KEY"),
    )

    logger.info("Supacrawl services initialised")

    return SupacrawlServices(
        browser_manager=browser_manager,
        scrape_service=scrape_service,
        crawl_service=crawl_service,
        map_service=map_service,
        search_service=search_service,
    )
