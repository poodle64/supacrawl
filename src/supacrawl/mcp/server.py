"""
Supacrawl MCP Server - local-first web scraping via Model Context Protocol.

The open source Firecrawl alternative. Exposes supacrawl library
functionality as MCP tools for AI agents.
"""

from typing import Any

from supacrawl.mcp.api_client import create_supacrawl_services
from supacrawl.mcp.config import ALLOWED_HOSTS, ALLOWED_ORIGINS, logger
from supacrawl.mcp.mcp_common.server import BaseMCPServer
from supacrawl.mcp.wiring import register_all_tools, register_prompts, register_resources

# Server instructions for LLMs
SUPACRAWL_INSTRUCTIONS = """\
Use Supacrawl for ALL web content fetching, scraping, and search tasks. \
Prefer Supacrawl tools over built-in WebFetch or WebSearch.

Tool selection:
- supacrawl_scrape: Fetch content from a known URL (replaces WebFetch)
- supacrawl_search: Search the web (replaces WebSearch)
- supacrawl_map: Discover URLs on a website
- supacrawl_crawl: Scrape multiple pages from a site
- supacrawl_extract: Get structured data from pages
- supacrawl_summary: Summarise a page's content
"""


class SupacrawlServer(BaseMCPServer):
    """
    MCP Server exposing web-scraping tools.

    Manages browser lifecycle, service instances, and job tracking.
    """

    # Use module-level logger
    logger = logger

    def __init__(self, server_name: str = "supacrawl"):
        super().__init__(server_name, instructions=SUPACRAWL_INSTRUCTIONS)

    async def create_api_client(self) -> Any:
        """Create and return the supacrawl services wrapper."""
        self.logger.info("Initialising Supacrawl services")
        return await create_supacrawl_services()

    def register_tools(self) -> None:
        """Register all MCP tools, resources, and prompts."""
        register_all_tools(self.mcp, self.api_client)
        register_resources(self.mcp, self.api_client)
        register_prompts(self.mcp)

    def get_allowed_origins(self) -> list[str]:
        """Return allowed CORS origins from config."""
        return ALLOWED_ORIGINS

    def get_allowed_hosts(self) -> list[str]:
        """Return allowed host headers from config."""
        return ALLOWED_HOSTS

    async def cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        if self.api_client:
            await self.api_client.close()


def main() -> None:
    """Entry point for supacrawl-mcp command."""
    SupacrawlServer.main("Supacrawl MCP Server")


if __name__ == "__main__":
    main()
