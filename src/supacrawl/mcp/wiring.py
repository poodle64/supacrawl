"""Tool registration wiring for Supacrawl MCP server.

Handles dynamic registration of MCP tools, resources, and prompts
using mcp-common patterns.
"""

import inspect

from fastmcp import FastMCP

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.config import logger
from supacrawl.mcp.mcp_common.tool_registration import create_tool_wrapper
from supacrawl.mcp.tools import crawl, diagnose, extract, health, scrape, search, summary
from supacrawl.mcp.tools import map as map_module


def register_all_tools(mcp: FastMCP, api_client: SupacrawlServices) -> None:
    """
    Register all Supacrawl MCP tools.

    Args:
        mcp: FastMCP server instance
        api_client: SupacrawlServices wrapper containing all services
    """
    if api_client is None:
        logger.error("Cannot register tools: API client is not initialized.")
        raise RuntimeError("API client must be initialized before registering tools.")

    # List all tool functions with their api_client
    # Each tool receives the SupacrawlServices wrapper as first argument
    #
    # NOTE: Agent tools are intentionally omitted. When using supacrawl via MCP,
    # the controlling LLM (Claude, ChatGPT, etc.) IS the agent - it orchestrates
    # the primitives below. See README for rationale.
    tool_functions = [
        # Core scraping tools
        (scrape.supacrawl_scrape, api_client),
        (map_module.supacrawl_map, api_client),
        (crawl.supacrawl_crawl, api_client),
        # Search tool
        (search.supacrawl_search, api_client),
        # LLM-assisted tools (scrape + context for calling LLM)
        (extract.supacrawl_extract, api_client),
        (summary.supacrawl_summary, api_client),
        # Operational
        (health.supacrawl_health, api_client),
        (diagnose.supacrawl_diagnose, api_client),
    ]

    tool_count = 0
    for tool_func, api_client_instance in tool_functions:
        # Verify it's a coroutine function
        if not inspect.iscoroutinefunction(tool_func):
            logger.warning(f"Skipping {tool_func.__name__}: not an async function")
            continue

        # Use mcp_common tool wrapper
        # The wrapper automatically removes 'api_client' from the signature and injects
        # it as the first argument when calling the tool function
        tool_wrapper = create_tool_wrapper(
            tool_func,
            api_client_instance,
        )
        mcp.tool(tool_wrapper)
        tool_count += 1

    logger.info(f"Registered {tool_count} Supacrawl tools")


def register_resources(mcp: FastMCP, api_client: SupacrawlServices | None = None) -> None:
    """
    Register all MCP resources for discoverability.

    Resources provide static/dynamic information about server capabilities
    that AI agents can use to understand available features.

    Args:
        mcp: FastMCP server instance
        api_client: Optional SupacrawlServices for dynamic status
    """
    from supacrawl.mcp import resources

    @mcp.resource("supacrawl://formats")
    async def formats_resource() -> str:
        """Get all supported output formats with descriptions."""
        return await resources.get_formats_resource()

    @mcp.resource("supacrawl://action_types")
    async def action_types_resource() -> str:
        """Get all supported page action types with examples."""
        return await resources.get_action_types_resource()

    @mcp.resource("supacrawl://search_providers")
    async def search_providers_resource() -> str:
        """Get available search providers and requirements."""
        return await resources.get_search_providers_resource()

    @mcp.resource("supacrawl://llm_config")
    async def llm_config_resource() -> str:
        """Get current LLM configuration and availability status."""
        return await resources.get_llm_config_resource()

    @mcp.resource("supacrawl://capabilities")
    async def capabilities_resource() -> str:
        """Get overall server capabilities, features, and limits."""
        return await resources.get_capabilities_resource(api_client)

    logger.info("Registered 5 MCP resources")


def register_prompts(mcp: FastMCP) -> None:
    """
    Register all MCP prompts for workflow guidance.

    Prompts provide structured guidance for AI agents to effectively
    use supacrawl tools for various web scraping tasks.

    Args:
        mcp: FastMCP server instance
    """
    from supacrawl.mcp import prompts

    @mcp.prompt()
    async def scrape_page() -> str:
        """Guide for basic page scraping with supacrawl_scrape."""
        return await prompts.get_scrape_page_prompt()

    @mcp.prompt()
    async def extract_structured_data() -> str:
        """Guide for structured data extraction."""
        return await prompts.get_extract_data_prompt()

    @mcp.prompt()
    async def summarise_page() -> str:
        """Guide for page summarisation."""
        return await prompts.get_summary_prompt()

    @mcp.prompt()
    async def crawl_website() -> str:
        """Guide for multi-page website crawling."""
        return await prompts.get_crawl_website_prompt()

    @mcp.prompt()
    async def research_topic() -> str:
        """Guide for multi-step web research using primitives."""
        return await prompts.get_research_topic_prompt()

    @mcp.prompt()
    async def select_tool() -> str:
        """Guide for choosing the right supacrawl tool."""
        return await prompts.get_select_tool_prompt()

    @mcp.prompt()
    async def search_web() -> str:
        """Guide for web search with optional result scraping."""
        return await prompts.get_search_web_prompt()

    @mcp.prompt()
    async def handle_errors() -> str:
        """Guide for error handling and troubleshooting."""
        return await prompts.get_handle_errors_prompt()

    logger.info("Registered 8 MCP prompts")
