"""Search, extraction, and agent commands."""

import asyncio
from pathlib import Path

import click

from supacrawl.cli._common import app


@app.command("search", help="Search the web using DuckDuckGo or Brave.")
@click.argument("query")
@click.option(
    "--limit",
    "-l",
    type=int,
    default=5,
    show_default=True,
    help="Maximum number of results (1-10) per source type.",
)
@click.option(
    "--source",
    "-s",
    "sources",
    multiple=True,
    type=click.Choice(["web", "images", "news", "all"], case_sensitive=False),
    default=["web"],
    show_default=True,
    help="Source types to search. Use 'all' for web+images+news.",
)
@click.option(
    "--scrape/--no-scrape",
    default=False,
    show_default=True,
    help="Scrape content from result pages (web results only).",
)
@click.option(
    "--provider",
    type=click.Choice(["duckduckgo", "brave"], case_sensitive=False),
    default="duckduckgo",
    show_default=True,
    help="Search provider to use.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Output file (JSON). If omitted, prints to stdout.",
)
def search(
    query: str,
    limit: int,
    sources: tuple[str, ...],
    scrape: bool,
    provider: str,
    output: Path | None,
) -> None:
    """Search the web and optionally scrape results.

    Examples:
        supacrawl search "python web scraping"
        supacrawl search "site:docs.python.org asyncio" --limit 10
        supacrawl search "AI startups 2024" --scrape --output results.json
        supacrawl search "product screenshots" --source images
        supacrawl search "tech news" --source news
        supacrawl search "AI announcements" --source web --source news
        supacrawl search "topic" --source all
    """
    import json

    from supacrawl.services.search import ScrapeOptions, SearchService

    # Expand "all" to individual source types
    source_list: list[str] = []
    for s in sources:
        if s.lower() == "all":
            source_list.extend(["web", "images", "news"])
        else:
            source_list.append(s.lower())

    # Remove duplicates while preserving order
    seen: set[str] = set()
    unique_sources: list[str] = []
    for s in source_list:
        if s not in seen:
            seen.add(s)
            unique_sources.append(s)

    async def run():
        # Create scrape service if scraping is requested
        scrape_service = None
        scrape_options = None

        if scrape:
            from supacrawl.services.scrape import ScrapeService

            scrape_service = ScrapeService()
            scrape_options = ScrapeOptions(formats=["markdown"], only_main_content=True)

        service = SearchService(
            scrape_service=scrape_service,
            provider=provider,  # type: ignore[arg-type]
        )

        try:
            result = await service.search(
                query=query,
                limit=limit,
                sources=unique_sources,  # type: ignore[arg-type]
                scrape_options=scrape_options,
            )
            return result
        finally:
            await service.close()

    result = asyncio.run(run())

    if not result.success:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    # Format output
    output_data = result.model_dump(exclude_none=True)
    json_str = json.dumps(output_data, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(json_str)
        click.echo(f"Wrote {len(result.data)} results to {output}")
    else:
        click.echo(json_str)


@app.command("llm-extract", help="Extract structured data from URLs using LLM.")
@click.argument("urls", nargs=-1, required=True)
@click.option(
    "--prompt",
    "-p",
    type=str,
    required=True,
    help="Extraction prompt describing what data to extract.",
)
@click.option(
    "--schema",
    "-s",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to JSON schema file for structured output.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Output file (JSON). If omitted, prints to stdout.",
)
def llm_extract(
    urls: tuple[str, ...],
    prompt: str,
    schema: Path | None,
    output: Path | None,
) -> None:
    """Extract structured data from URLs using LLM.

    Requires LLM environment variables:
        SUPACRAWL_LLM_PROVIDER=ollama|openai|anthropic
        SUPACRAWL_LLM_MODEL=<model-name>
        OPENAI_API_KEY or ANTHROPIC_API_KEY  (for cloud providers)

    Examples:
        supacrawl llm-extract https://example.com/product -p "Extract product name and price"
        supacrawl llm-extract https://example.com -p "Extract contact info" -s schema.json
        supacrawl llm-extract https://a.com https://b.com -p "Extract titles"
    """
    import json

    from supacrawl.services.extract import ExtractService
    from supacrawl.services.scrape import ScrapeService

    # Load schema if provided
    schema_dict = None
    if schema:
        with open(schema) as f:
            schema_dict = json.load(f)

    async def run():
        scrape_service = ScrapeService()
        service = ExtractService(scrape_service=scrape_service)

        try:
            result = await service.extract(
                urls=list(urls),
                prompt=prompt,
                schema=schema_dict,
            )
            return result
        finally:
            await service.close()

    result = asyncio.run(run())

    if not result.success:
        click.echo(f"Error: {result.error}", err=True)
        # Still output partial results if available
        if not result.data:
            raise SystemExit(1)

    # Format output
    output_data = result.model_dump(exclude_none=True)
    json_str = json.dumps(output_data, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(json_str)
        successful = sum(1 for item in result.data if item.success)
        click.echo(f"Extracted from {successful}/{len(result.data)} URLs to {output}")
    else:
        click.echo(json_str)


@app.command("agent", help="Run autonomous web agent for data gathering.")
@click.argument("prompt")
@click.option(
    "--url",
    "-u",
    "urls",
    multiple=True,
    help="Starting URLs (can be specified multiple times). If omitted, agent searches first.",
)
@click.option(
    "--schema",
    "-s",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to JSON schema file for structured output.",
)
@click.option(
    "--max-steps",
    type=int,
    default=10,
    show_default=True,
    help="Maximum pages to visit.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Output file (JSON). If omitted, prints to stdout.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress progress output, only show final result.",
)
def agent_cmd(
    prompt: str,
    urls: tuple[str, ...],
    schema: Path | None,
    max_steps: int,
    output: Path | None,
    quiet: bool,
) -> None:
    """Run autonomous web agent to gather data.

    The agent will search the web, visit relevant pages, and extract
    information based on your prompt.

    Requires LLM environment variables:
        SUPACRAWL_LLM_PROVIDER=ollama|openai|anthropic
        SUPACRAWL_LLM_MODEL=<model-name>
        OPENAI_API_KEY or ANTHROPIC_API_KEY  (for cloud providers)

    Examples:
        supacrawl agent "Find AI startups founded in 2024"
        supacrawl agent "Find product pricing" -u https://example.com/pricing
        supacrawl agent "Find tech news" --max-steps 20 --output results.json
    """
    import json

    from supacrawl.services.agent import AgentService
    from supacrawl.services.scrape import ScrapeService
    from supacrawl.services.search import SearchService

    # Load schema if provided
    schema_dict = None
    if schema:
        with open(schema) as f:
            schema_dict = json.load(f)

    async def run():
        scrape_service = ScrapeService()
        search_service = SearchService(scrape_service=scrape_service)
        agent = AgentService(
            scrape_service=scrape_service,
            search_service=search_service,
        )

        try:
            # Stream events unless quiet mode
            if quiet:
                result = await agent.run_sync(
                    prompt=prompt,
                    urls=list(urls) if urls else None,
                    schema=schema_dict,
                    max_steps=max_steps,
                )
                return result
            else:
                # Stream events to stderr, return final result
                final_result = None
                async for event in agent.run(
                    prompt=prompt,
                    urls=list(urls) if urls else None,
                    schema=schema_dict,
                    max_steps=max_steps,
                ):
                    if event.type == "thinking":
                        click.echo(f"💭 {event.message}", err=True)
                    elif event.type == "action":
                        click.echo(f"🔍 {event.message}", err=True)
                    elif event.type == "result":
                        click.echo(f"✓ {event.message}", err=True)
                    elif event.type == "error":
                        click.echo(f"✗ {event.message}", err=True)
                    elif event.type == "complete":
                        click.echo(f"\n✅ {event.message}", err=True)
                        from supacrawl.models import AgentResult

                        final_result = AgentResult(
                            success=True,
                            data=event.data,
                            urls_visited=[],  # Not tracked in streaming mode
                        )

                return final_result
        finally:
            await search_service.close()
            await agent.close()

    result = asyncio.run(run())

    if result is None or not result.success:
        error_msg = result.error if result else "Agent failed"
        click.echo(f"Error: {error_msg}", err=True)
        raise SystemExit(1)

    # Format output
    output_data = result.model_dump(exclude_none=True)
    json_str = json.dumps(output_data, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(json_str)
        click.echo(f"Wrote results to {output}")
    else:
        click.echo(json_str)
