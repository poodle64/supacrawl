"""Command-line interface for web-scraper."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import click

from web_scraper.config import default_corpora_dir, default_sites_dir
from web_scraper.content.fixes import get_fix_index
from web_scraper.corpus.compress import compress_snapshot, extract_archive
from web_scraper.exceptions import WebScrapeError
from web_scraper.prep.chunker import chunk_snapshot
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
from web_scraper.sites.loader import list_site_configs, load_site_config


def _load_env_file(env_path: Path | None = None) -> None:
    """
    Load environment variables from .env file if it exists.

    Args:
        env_path: Optional path to .env file. If None, looks for .env in current directory.
    """
    if env_path is None:
        env_path = Path.cwd() / ".env"

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse key=value pairs
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                # Only set if not already in environment
                if key and key not in os.environ:
                    os.environ[key] = value


# Load .env file when CLI module is imported
_load_env_file()


def _configure_logging(verbose: bool) -> None:
    """Configure root logging level once."""
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(message)s",
    )


@click.group(help="Generic website ingestion pipeline.")
def app() -> None:
    """
    Entry point for the web-scraper CLI.

    Provides commands for listing sites, showing site details, crawling sites,
    and chunking snapshots.
    """


@app.command("list-sites", help="List available site configuration files.")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ and corpora/ folders.",
)
def list_sites(base_path: Path | None) -> None:
    """
    List available site configuration files.

    Args:
        base_path: Optional base directory containing sites/ folder.
    """
    sites_dir = default_sites_dir(base_path)
    configs = list_site_configs(sites_dir)
    if not configs:
        click.echo(f"No site configurations found in {sites_dir}")
        return
    for config in configs:
        click.echo(config.name)


@app.command("show-site", help="Show a summary for a site configuration.")
@click.argument("site_name")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ and corpora/ folders.",
)
def show_site(site_name: str, base_path: Path | None) -> None:
    """
    Display site configuration details.

    Args:
        site_name: Name of the site configuration (without .yaml extension).
        base_path: Optional base directory containing sites/ folder.

    Raises:
        click.ClickException: If the site configuration is not found or invalid.
    """
    sites_dir = default_sites_dir(base_path)
    try:
        config = load_site_config(site_name, sites_dir)
    except WebScrapeError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
        raise SystemExit(1) from exc

    click.echo(f"ID: {config.id}")
    click.echo(f"Name: {config.name}")
    click.echo(f"Entrypoints: {', '.join(config.entrypoints)}")
    click.echo(f"Include: {', '.join(config.include)}")
    click.echo(f"Exclude: {', '.join(config.exclude)}")
    click.echo(f"Max pages: {config.max_pages}")
    click.echo(f"Formats: {', '.join(config.formats)}")
    click.echo(f"Only main content: {config.only_main_content}")
    click.echo(f"Include subdomains: {config.include_subdomains}")
    click.echo(f"Sitemap enabled: {config.sitemap.enabled}")
    if config.sitemap.urls:
        click.echo(f"Sitemap URLs: {', '.join(config.sitemap.urls)}")
    click.echo(f"Robots.txt: {config.robots.enforcement} ({config.robots.user_agent})")
    fixes_status = "enabled" if config.markdown_fixes.enabled else "disabled"
    if config.markdown_fixes.fixes:
        disabled_fixes = [
            name for name, enabled in config.markdown_fixes.fixes.items() if not enabled
        ]
        if disabled_fixes:
            fixes_status += f" (disabled: {', '.join(disabled_fixes)})"
    click.echo(f"Markdown fixes: {fixes_status}")


@app.command("crawl-url", help="Crawl a website (Firecrawl-compatible API).")
@click.argument("url")
@click.option(
    "--limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum pages to crawl",
)
@click.option(
    "--depth",
    type=int,
    default=3,
    show_default=True,
    help="Maximum crawl depth",
)
@click.option(
    "--include",
    multiple=True,
    help="URL patterns to include (glob patterns)",
)
@click.option(
    "--exclude",
    multiple=True,
    help="URL patterns to exclude (glob patterns)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Output directory for scraped content",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume from previous crawl",
)
def crawl_url(
    url: str,
    limit: int,
    depth: int,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    output: Path,
    resume: bool,
) -> None:
    """Crawl a website and save all pages (Firecrawl-compatible).

    Examples:
        web-scraper crawl-url https://example.com --limit 50 --output corpus/
        web-scraper crawl-url https://example.com --output corpus/ --resume
        web-scraper crawl-url https://example.com --include "*/docs/*" --output corpus/
    """
    import asyncio

    from web_scraper.crawl_service import CrawlService

    async def run():
        service = CrawlService()
        async for event in service.crawl(
            url=url,
            limit=limit,
            max_depth=depth,
            include_patterns=list(include) if include else None,
            exclude_patterns=list(exclude) if exclude else None,
            output_dir=output,
            resume=resume,
        ):
            if event.type == "progress":
                click.echo(f"Progress: {event.completed}/{event.total}", err=True)
            elif event.type == "page":
                click.echo(f"Scraped: {event.url}")
            elif event.type == "error":
                click.echo(f"Error: {event.url}: {event.error}", err=True)
            elif event.type == "complete":
                click.echo(f"\nComplete: {event.completed}/{event.total} pages", err=True)

    asyncio.run(run())


@app.command("scrape-url", help="Scrape a single URL (Firecrawl-compatible API).")
@click.argument("url")
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    type=click.Choice(["markdown", "html", "rawHtml", "links"], case_sensitive=False),
    default=["markdown"],
    show_default=True,
    help="Output formats to include",
)
@click.option(
    "--only-main-content/--no-only-main-content",
    default=True,
    show_default=True,
    help="Extract main content area only",
)
@click.option(
    "--wait-for",
    type=int,
    default=0,
    show_default=True,
    help="Additional wait time in ms after page load",
)
@click.option(
    "--timeout",
    type=int,
    default=30000,
    show_default=True,
    help="Page load timeout in ms",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Output file (JSON). If omitted, prints markdown to stdout.",
)
def scrape_url(
    url: str,
    formats: tuple[str, ...],
    only_main_content: bool,
    wait_for: int,
    timeout: int,
    output: Path | None,
) -> None:
    """Scrape a single URL and extract content (Firecrawl-compatible).

    Examples:
        web-scraper scrape-url https://example.com
        web-scraper scrape-url https://example.com --format markdown --format html
        web-scraper scrape-url https://example.com --output page.json
    """
    import asyncio
    import json

    from web_scraper.scrape_service import ScrapeService

    async def run():
        service = ScrapeService()
        result = await service.scrape(
            url=url,
            formats=list(formats),  # type: ignore[arg-type]
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
        )
        return result

    result = asyncio.run(run())

    # Handle errors
    if not result.success:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    # Output handling
    if output:
        with open(output, "w") as f:
            json.dump(result.model_dump(), f, indent=2)
        click.echo(f"Wrote scrape result to {output}")
    else:
        # Print markdown to stdout
        if result.data and result.data.markdown:
            click.echo(result.data.markdown)
        else:
            click.echo("No markdown content available", err=True)
            raise SystemExit(1)


@app.command("map-url", help="Map URLs from a website (Firecrawl-compatible API).")
@click.argument("url")
@click.option(
    "--limit",
    type=int,
    default=200,
    show_default=True,
    help="Maximum number of URLs to discover.",
)
@click.option(
    "--depth",
    type=int,
    default=3,
    show_default=True,
    help="Maximum BFS crawl depth.",
)
@click.option(
    "--sitemap",
    type=click.Choice(["include", "skip", "only"], case_sensitive=False),
    default="include",
    show_default=True,
    help="Sitemap handling: include (default), skip, or only.",
)
@click.option(
    "--include-subdomains",
    is_flag=True,
    default=False,
    help="Include subdomain URLs.",
)
@click.option(
    "--search",
    type=str,
    default=None,
    help="Filter URLs containing this text.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Output file (JSON). If omitted, prints URLs to stdout.",
)
def map_url(
    url: str,
    limit: int,
    depth: int,
    sitemap: str,
    include_subdomains: bool,
    search: str | None,
    output: Path | None,
) -> None:
    """Map a website to discover all URLs (Firecrawl-compatible).

    Examples:
        web-scraper map-url https://example.com
        web-scraper map-url https://example.com --limit 50 --output urls.json
        web-scraper map-url https://example.com --search about --sitemap skip
    """
    import asyncio
    import json

    from web_scraper.map_service import MapService

    async def run():
        service = MapService()
        result = await service.map(
            url=url,
            limit=limit,
            max_depth=depth,
            sitemap=sitemap,  # type: ignore[arg-type]
            include_subdomains=include_subdomains,
            search=search,
        )
        return result

    result = asyncio.run(run())

    # Handle errors
    if not result.success:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    # Output handling
    if output:
        with open(output, "w") as f:
            json.dump(result.model_dump(), f, indent=2)
        click.echo(f"Wrote {len(result.links)} URLs to {output}")
    else:
        # Print URLs to stdout (one per line)
        for link in result.links:
            click.echo(link.url)


@app.command("map", help="Map site URLs that would be crawled (Firecrawl-style discovery).")
@click.argument("site_name")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ folder.",
)
@click.option(
    "--max-urls",
    type=int,
    default=200,
    show_default=True,
    help="Maximum number of URLs to return.",
)
@click.option(
    "--format",
    type=click.Choice(["json", "jsonl"], case_sensitive=False),
    default="jsonl",
    show_default=True,
    help="Output format: json (pretty) or jsonl (one object per line).",
)
@click.option(
    "--output",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Output file path. If omitted, prints to stdout.",
)
@click.option(
    "--use-sitemap/--no-sitemap",
    default=None,
    help="Override config.sitemap.enabled (default: use config).",
)
@click.option(
    "--use-robots/--no-robots",
    default=None,
    help="Override config.robots.respect (default: use config).",
)
@click.option(
    "--include-entrypoints-only",
    is_flag=True,
    default=False,
    help="Return only entrypoints, no discovery.",
)
@click.option(
    "--browser",
    is_flag=True,
    default=False,
    help="Use browser rendering for link discovery (required for SPAs with JS-rendered links).",
)
def map_site(
    site_name: str,
    base_path: Path | None,
    max_urls: int,
    format: str,
    output: Path | None,
    use_sitemap: bool | None,
    use_robots: bool | None,
    include_entrypoints_only: bool,
    browser: bool,
) -> None:
    """
    Map a site to discover all URLs that would be crawled.

    Discovers URLs from entrypoints, sitemaps, and HTML links (one hop),
    applying include/exclude patterns and robots.txt rules.

    Args:
        site_name: Name of the site configuration (without .yaml extension).
        base_path: Optional base directory containing sites/ folder.
        max_urls: Maximum number of URLs to return.
        format: Output format (json or jsonl).
        output: Output file path (or stdout if omitted).
        use_sitemap: Override sitemap discovery.
        use_robots: Override robots.txt enforcement.
        include_entrypoints_only: Return only entrypoints.
        browser: Use Playwright for browser-rendered link discovery.
    """
    import json

    from web_scraper.map import map_site as map_site_func

    sites_dir = default_sites_dir(base_path)

    try:
        config = load_site_config(site_name, sites_dir)
    except WebScrapeError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
        raise SystemExit(1) from exc

    # Run mapping
    try:
        url_entries = asyncio.run(
            map_site_func(
                config,
                max_urls=max_urls,
                include_entrypoints_only=include_entrypoints_only,
                use_sitemap=use_sitemap,
                use_robots=use_robots,
                use_browser=browser,
            )
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

    # Serialise output
    if format.lower() == "json":
        content = json.dumps(url_entries, indent=2, ensure_ascii=False)
    else:  # jsonl
        lines = [json.dumps(entry, ensure_ascii=False) for entry in url_entries]
        content = "\n".join(lines) + "\n"

    # Write to file or stdout
    if output:
        output.write_text(content, encoding="utf-8")
        click.echo(f"Mapped {len(url_entries)} URLs to {output}", err=True)
    else:
        click.echo(content)


@app.command("crawl", help="Run a crawl for a site.")
@click.argument("site_name")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ and corpora/ folders.",
)
@click.option(
    "--verbose/--no-verbose",
    default=False,
    show_default=True,
    help="Show crawl progress logs.",
)
@click.option(
    "--fresh",
    is_flag=True,
    default=False,
    help="Start a new snapshot even if an incomplete one exists.",
)
@click.option(
    "--formats",
    type=str,
    default=None,
    help="Comma-separated output formats (markdown, html, text, json). Overrides config.",
)
@click.option(
    "--from-map",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Crawl only the URLs in a map output file (json or jsonl).",
)
@click.option(
    "--concurrency",
    type=int,
    default=None,
    help="Maximum concurrent page crawls (1-20). Overrides config.politeness.max_concurrent.",
)
@click.option(
    "--delay",
    type=float,
    default=None,
    help="Minimum delay between requests in seconds. Overrides config.politeness.delay_between_requests.",
)
@click.option(
    "--timeout",
    type=float,
    default=None,
    help="Page timeout in seconds (5-600). Overrides config.politeness.page_timeout.",
)
@click.option(
    "--retries",
    type=int,
    default=None,
    help="Maximum retry attempts (0-10). Overrides config.politeness.max_retries.",
)
@click.option(
    "--chunks",
    is_flag=True,
    default=False,
    help="Generate chunks.jsonl after crawl completes.",
)
@click.option(
    "--max-chars",
    type=int,
    default=1200,
    show_default=True,
    help="Maximum characters per chunk (used with --chunks).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show URLs that would be crawled without fetching content.",
)
@click.option(
    "--init",
    type=str,
    default=None,
    help="Create site config from URL before crawling.",
)
@click.option(
    "--provider",
    type=click.Choice(["crawl4ai", "playwright"], case_sensitive=False),
    default="crawl4ai",
    show_default=True,
    help="Scraping provider: crawl4ai (default) or playwright (for SPAs with routing issues).",
)
def crawl(
    site_name: str,
    base_path: Path | None,
    verbose: bool,
    fresh: bool,
    formats: str | None,
    from_map: Path | None,
    concurrency: int | None,
    delay: float | None,
    timeout: float | None,
    retries: int | None,
    chunks: bool,
    max_chars: int,
    dry_run: bool,
    init: str | None,
    provider: str,
) -> None:
    """
    Crawl a site and write a snapshot.

    Args:
        site_name: Name of the site configuration (without .yaml extension), or a URL when using --init.
        base_path: Optional base directory containing sites/ and corpora/ folders.
        verbose: Show detailed progress logs.
        fresh: Start a new snapshot even if an incomplete one exists.
        formats: Comma-separated output formats.
        from_map: Path to JSON or JSONL map file. If provided, crawl only URLs from map.
        concurrency: Override max concurrent page crawls.
        delay: Override minimum delay between requests.
        timeout: Override page timeout.
        retries: Override max retry attempts.
        chunks: Generate chunks.jsonl after crawl completes.
        max_chars: Maximum characters per chunk.
        dry_run: Show URLs that would be crawled without fetching content.
        init: Site name for URL quick-start (use with URL as site_name argument).
        provider: Scraping provider to use (crawl4ai or playwright).

    Raises:
        click.ClickException: If the site configuration is not found or invalid.
    """
    from web_scraper.corpus.state import (
        find_resumable_snapshot,
        load_state,
    )

    _configure_logging(verbose)
    sites_dir = default_sites_dir(base_path)
    corpora_dir = default_corpora_dir(base_path)

    # Handle URL quick-start: if site_name looks like a URL, require --init
    if site_name.startswith("http://") or site_name.startswith("https://"):
        if not init:
            click.echo(
                "Error: When using a URL as the first argument, you must provide --init <site_name>",
                err=True,
            )
            click.echo("Example: web-scraper crawl https://example.com --init my-site", err=True)
            raise SystemExit(1)

        # Create site config from URL
        from web_scraper.init import scaffold_site_config

        url = site_name
        actual_site_name = init

        try:
            config_path = scaffold_site_config(
                site_name=actual_site_name,
                sites_dir=sites_dir,
                url=url,
                interactive=False,
            )
            if verbose:
                click.echo(f"Created {config_path}")
        except click.ClickException as exc:
            click.echo(f"Error: {exc.message}", err=True)
            raise SystemExit(1) from exc
        except Exception as exc:
            click.echo(f"Error creating config: {exc}", err=True)
            raise SystemExit(1) from exc

        # Now use the created config
        site_name = actual_site_name

    try:
        config = load_site_config(site_name, sites_dir)
    except WebScrapeError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
        raise SystemExit(1) from exc

    # Handle dry-run mode
    if dry_run:
        import asyncio

        from web_scraper.map import map_site as map_site_func

        try:
            url_entries = asyncio.run(
                map_site_func(config, max_urls=config.max_pages)
            )
            for entry in url_entries:
                url = entry.get("url", entry) if isinstance(entry, dict) else entry
                click.echo(url)
            click.echo(f"\n{len(url_entries)} URLs would be crawled")
        except Exception as exc:
            click.echo(f"Error during URL discovery: {exc}", err=True)
            raise SystemExit(1) from exc
        return  # Exit without crawling

    # Handle map file if provided
    target_urls: list[str] | None = None
    if from_map:
        from web_scraper.map_io import load_map_entries, select_crawl_urls

        try:
            # Load map entries
            map_entries = load_map_entries(from_map)
            if verbose:
                click.echo(f"Loaded {len(map_entries)} entries from map file")

            # Select crawl URLs (default filter: included=true and allowed=true if present)
            target_urls = select_crawl_urls(map_entries)
            if verbose:
                click.echo(f"Selected {len(target_urls)} URLs from map for crawling")

        except Exception as exc:
            click.echo(f"Error loading map file: {exc}", err=True)
            raise SystemExit(1) from exc

    # Override formats if specified
    if formats:
        format_list = [f.strip() for f in formats.split(",") if f.strip()]
        if format_list:
            # Validate and update config formats
            from web_scraper.models import OutputFormat
            try:
                validated = []
                for fmt in format_list:
                    OutputFormat.from_string(fmt)  # Validate
                    validated.append(fmt.lower())
                config = config.model_copy(update={"formats": validated})
                if verbose:
                    click.echo(f"Output formats: {', '.join(validated)}")
            except ValueError as e:
                click.echo(f"Error: Invalid format: {e}", err=True)
                raise SystemExit(1) from e

    # Apply politeness overrides from CLI
    politeness_updates: dict[str, object] = {}
    if concurrency is not None:
        if not 1 <= concurrency <= 20:
            click.echo("Error: --concurrency must be between 1 and 20", err=True)
            raise SystemExit(1)
        politeness_updates["max_concurrent"] = concurrency
    if delay is not None:
        if delay < 0:
            click.echo("Error: --delay must be non-negative", err=True)
            raise SystemExit(1)
        # Set both min and max to the same value for consistent delay
        politeness_updates["delay_between_requests"] = (delay, delay + 0.5)
    if timeout is not None:
        if not 5.0 <= timeout <= 600.0:
            click.echo("Error: --timeout must be between 5 and 600 seconds", err=True)
            raise SystemExit(1)
        politeness_updates["page_timeout"] = timeout
    if retries is not None:
        if not 0 <= retries <= 10:
            click.echo("Error: --retries must be between 0 and 10", err=True)
            raise SystemExit(1)
        politeness_updates["max_retries"] = retries

    if politeness_updates:
        new_politeness = config.politeness.model_copy(update=politeness_updates)
        config = config.model_copy(update={"politeness": new_politeness})
        if verbose:
            click.echo(
                f"Politeness settings: concurrency={config.politeness.max_concurrent}, "
                f"delay={config.politeness.delay_between_requests}, "
                f"timeout={config.politeness.page_timeout}s, "
                f"retries={config.politeness.max_retries}"
            )

    # Auto-resume logic
    resume_snapshot: Path | None = None
    completed_pages = 0
    if not fresh:
        assert config.id is not None, "config.id must be set after validation"
        resume_snapshot = find_resumable_snapshot(corpora_dir, config.id)
        if resume_snapshot:
            state = load_state(resume_snapshot)
            if state:
                completed_pages = state.checkpoint_page
                pending_pages = max(0, config.max_pages - completed_pages)
                click.echo(
                    f"Resuming {config.name} ({completed_pages} completed, "
                    f"{pending_pages} pending)..."
                )

    if fresh:
        # Check if there was an incomplete snapshot we're ignoring
        assert config.id is not None, "config.id must be set after validation"
        incomplete = find_resumable_snapshot(corpora_dir, config.id)
        if incomplete:
            click.echo(f"Starting fresh crawl for {config.name}...")
        else:
            click.echo(f"Starting crawl for {config.name}...")
    elif not resume_snapshot:
        click.echo(f"Starting crawl for {config.name}...")

    # Create scraper based on provider selection
    # Playwright provider requires target_urls (no link discovery)
    if provider.lower() == "playwright":
        from web_scraper.scrapers.playwright_scraper import PlaywrightScraper

        # Playwright requires explicit URL list - use from_map or entrypoints
        if target_urls is None:
            # Use entrypoints as target URLs for Playwright
            target_urls = list(config.entrypoints)
            if verbose:
                click.echo(
                    f"Playwright provider: using {len(target_urls)} entrypoints as target URLs"
                )
                click.echo(
                    "Note: Playwright does not discover links. Use --from-map for multi-page crawls."
                )

        scraper = PlaywrightScraper()
        if verbose:
            click.echo("Using Playwright provider (SPA-compatible)")
    else:
        scraper = Crawl4AIScraper()
        if verbose:
            click.echo("Using Crawl4AI provider")

    try:
        pages, snapshot_path = scraper.crawl(
            config,
            corpora_dir,
            resume_snapshot=resume_snapshot,
            target_urls=target_urls,
        )

        # Generate chunks if requested
        chunk_count = 0
        if chunks:
            import asyncio

            from web_scraper.prep.chunker import chunk_snapshot
            chunks_path = asyncio.run(chunk_snapshot(snapshot_path, max_chars=max_chars))
            # Count chunks
            chunk_count = sum(1 for _ in chunks_path.read_text().splitlines())

        # Output summary
        assert config.id is not None, "config.id must be set after validation"
        if chunks:
            click.echo(f"Crawled {len(pages)} pages, generated {chunk_count} chunks")
        else:
            click.echo(f"Crawled {len(pages)} pages")

        # Show output path - use relative path if base_path not provided, else show from base
        if base_path is None:
            click.echo(f"Output: corpora/{config.id}/latest/")
        else:
            click.echo(f"Output: {base_path}/corpora/{config.id}/latest/")
        if verbose:
            click.echo(f"Snapshot ID: {snapshot_path.name}")
    except KeyboardInterrupt:
        # Handle Ctrl+C at CLI level as fallback
        click.echo("\nCrawl interrupted.", err=True)
        raise SystemExit(130)  # Standard exit code for SIGINT
    except Exception as exc:
        # Check for CrawlInterrupted (graceful shutdown with saved state)
        from web_scraper.exceptions import CrawlInterrupted
        if isinstance(exc, CrawlInterrupted):
            click.echo(f"\nCrawl interrupted. Progress saved: {exc.pages_completed} pages.", err=True)
            click.echo(f"Resume: web-scraper crawl {site_name}", err=True)
            raise SystemExit(130)
        raise


@app.command("list-snapshots", help="List snapshots for a site.")
@click.argument("site_name")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing corpora/ folder.",
)
def list_snapshots(site_name: str, base_path: Path | None) -> None:
    """
    List all snapshots for a site with metadata.

    Args:
        site_name: Name of the site.
        base_path: Optional base directory containing corpora/ folder.
    """
    import json

    from web_scraper.corpus.symlink import LATEST_SYMLINK_NAME

    corpora_dir = default_corpora_dir(base_path)
    site_dir = corpora_dir / site_name

    if not site_dir.exists():
        click.echo(f"No snapshots found for site: {site_name}")
        return

    snapshots = []
    for item in site_dir.iterdir():
        # Skip the 'latest' symlink
        if item.name == LATEST_SYMLINK_NAME:
            continue
        if not item.is_dir():
            continue

        manifest_path = item / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
            status = manifest.get("status", "unknown")
            total_pages = manifest.get("total_pages", 0)
            created_at = manifest.get("created_at", "unknown")

            # Check for chunks
            chunks_path = item / "chunks.jsonl"
            if chunks_path.exists():
                chunk_count = sum(1 for _ in chunks_path.read_text().splitlines())
            else:
                chunk_count = None

            snapshots.append({
                "id": item.name,
                "status": status,
                "pages": total_pages,
                "chunks": chunk_count,
                "created_at": created_at,
            })
        except Exception:
            continue

    # Sort by snapshot ID descending (most recent first)
    snapshots.sort(key=lambda s: s["id"], reverse=True)

    if not snapshots:
        click.echo(f"No snapshots found for site: {site_name}")
        return

    # Print table
    for snap in snapshots:
        chunks_str = f"{snap['chunks']:>4}" if snap['chunks'] is not None else "   -"
        click.echo(
            f"{snap['id']}  {snap['status']:<10}  {snap['pages']:>4} pages  "
            f"{chunks_str} chunks  {snap['created_at']}"
        )


@app.command("init", help="Create a new site configuration.")
@click.argument("site_name")
@click.option(
    "--url",
    type=str,
    default=None,
    help="Starting URL for the site.",
)
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ folder.",
)
def init(site_name: str, url: str | None, base_path: Path | None) -> None:
    """
    Create a new site configuration file.

    Args:
        site_name: Site identifier (becomes filename without .yaml).
        url: Optional starting URL.
        base_path: Optional base directory.
    """
    from web_scraper.init import scaffold_site_config

    sites_dir = default_sites_dir(base_path)

    try:
        config_path = scaffold_site_config(
            site_name=site_name,
            sites_dir=sites_dir,
            url=url,
            interactive=(url is None),
        )
        click.echo(f"Created {config_path}")
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


@app.command("chunk", help="Chunk a snapshot into JSONL output.")
@click.argument("site_id")
@click.argument("snapshot_id")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ and corpora/ folders.",
)
@click.option(
    "--max-chars",
    type=int,
    default=1200,
    show_default=True,
    help="Approximate maximum characters per chunk.",
)
@click.option(
    "--use-ollama",
    is_flag=True,
    default=False,
    help="Use Ollama for processing (requires Ollama running on localhost:11434).",
)
@click.option(
    "--ollama-model",
    type=str,
    default=None,
    help="Ollama model to use (defaults to OLLAMA_MODEL env var or 'llama3.2').",
)
@click.option(
    "--ollama-summarize",
    is_flag=True,
    default=False,
    help="Add summaries to chunks using Ollama (requires --use-ollama).",
)
def chunk(
    site_id: str,
    snapshot_id: str,
    base_path: Path | None,
    max_chars: int,
    use_ollama: bool,
    ollama_model: str | None,
    ollama_summarize: bool,
) -> None:
    """
    Chunk snapshot pages into JSONL records.

    Args:
        site_id: Site identifier.
        snapshot_id: Snapshot identifier.
        base_path: Optional base directory containing corpora/ folder.
        max_chars: Maximum characters per chunk. Defaults to 1200.
        use_ollama: Whether to use Ollama for processing.
        ollama_model: Ollama model to use.
        ollama_summarize: Whether to add summaries to chunks using Ollama.

    Raises:
        click.ClickException: If the snapshot is not found or chunking fails.
    """
    corpora_dir = default_corpora_dir(base_path)
    snapshot_path = corpora_dir / site_id / snapshot_id
    if not snapshot_path.exists():
        msg = f"Snapshot not found at {snapshot_path}. Check that the site_id and snapshot_id are correct."
        click.echo(f"Error: {msg}", err=True)
        raise SystemExit(1)

    if ollama_summarize and not use_ollama:
        click.echo(
            "Error: --ollama-summarize requires --use-ollama", err=True
        )
        raise SystemExit(1)

    try:
        output_path = asyncio.run(
            chunk_snapshot(
                snapshot_path,
                max_chars=max_chars,
                use_ollama=use_ollama,
                ollama_model=ollama_model,
                ollama_summarize=ollama_summarize,
            )
        )
        # Count chunks
        chunk_count = sum(1 for _ in output_path.read_text().splitlines())
        click.echo(f"Generated {chunk_count} chunks")
        # Show output path - respect base_path
        if base_path is None:
            if snapshot_id == "latest":
                click.echo(f"Output: corpora/{site_id}/latest/chunks.jsonl")
            else:
                click.echo(f"Output: corpora/{site_id}/{snapshot_id}/chunks.jsonl")
        else:
            if snapshot_id == "latest":
                click.echo(f"Output: {base_path}/corpora/{site_id}/latest/chunks.jsonl")
            else:
                click.echo(f"Output: {base_path}/corpora/{site_id}/{snapshot_id}/chunks.jsonl")
    except WebScrapeError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
        raise SystemExit(1) from exc


@app.command("compress", help="Compress a snapshot for archival.")
@click.argument("site_id")
@click.argument("snapshot_id")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing corpora/ folder.",
)
@click.option(
    "--mode",
    type=click.Choice(["archive", "gzip", "none"]),
    default="archive",
    show_default=True,
    help="Compression mode: 'archive' creates .tar.gz, 'gzip' compresses each file.",
)
@click.option(
    "--keep-originals",
    is_flag=True,
    default=False,
    help="Keep original files after compression.",
)
def compress(
    site_id: str,
    snapshot_id: str,
    base_path: Path | None,
    mode: str,
    keep_originals: bool,
) -> None:
    """
    Compress a snapshot for archival or transfer.

    Args:
        site_id: Site identifier.
        snapshot_id: Snapshot identifier.
        base_path: Optional base directory containing corpora/ folder.
        mode: Compression mode (archive, gzip, none).
        keep_originals: If True, keep original files.
    """
    corpora_dir = default_corpora_dir(base_path)
    snapshot_path = corpora_dir / site_id / snapshot_id

    if not snapshot_path.exists():
        click.echo(f"Error: Snapshot not found at {snapshot_path}", err=True)
        raise SystemExit(1)

    try:
        output_path = compress_snapshot(
            snapshot_path,
            mode=mode,  # type: ignore[arg-type]
            remove_originals=not keep_originals,
        )
        if mode == "archive":
            click.echo(f"Archive created: {output_path}")
        elif mode == "gzip":
            click.echo(f"Files compressed in: {output_path}")
        else:
            click.echo("No compression applied.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


@app.command("extract", help="Extract a compressed snapshot archive.")
@click.argument("archive_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--target-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Directory to extract to. Defaults to archive location.",
)
def extract(archive_path: Path, target_dir: Path | None) -> None:
    """
    Extract a compressed snapshot archive.

    Args:
        archive_path: Path to the .tar.gz archive.
        target_dir: Optional target directory for extraction.
    """
    try:
        output_path = extract_archive(archive_path, target_dir)
        click.echo(f"Extracted to: {output_path}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


@app.command("parity", hidden=True, help="[Dev] Run Firecrawl parity comparison harness.")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("docs/parity"),
    help="Directory for parity report output (default: docs/parity).",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Force re-fetch (ignore cache).",
)
@click.option(
    "--cache-only",
    is_flag=True,
    default=False,
    help="Only use cache, fail if missing.",
)
@click.option(
    "--urls-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Optional file with URLs to test (one per line, overrides default).",
)
@click.option(
    "--max-urls",
    type=int,
    default=None,
    help="Maximum number of URLs to process.",
)
def parity(
    output_dir: Path,
    no_cache: bool,
    cache_only: bool,
    urls_file: Path | None,
    max_urls: int | None,
) -> None:
    """
    Run Firecrawl parity comparison to evaluate fixes subsystem.

    This is a development command for comparing web-scraper output against Firecrawl.
    It is hidden from the main help output.

    Compares web-scraper output (baseline-static vs enhanced) against Firecrawl
    to make evidence-based decision on whether fixes subsystem should be kept.

    Requires FIRECRAWL_API_KEY environment variable for Firecrawl comparisons.
    """
    from tools.parity.cache import load_urls_from_file
    from tools.parity.harness import run_parity_comparison
    from tools.parity.report import generate_json_report, generate_markdown_report

    try:
        # Load URLs if file provided
        urls = None
        if urls_file:
            urls = load_urls_from_file(urls_file)
            click.echo(f"Loaded {len(urls)} URLs from {urls_file}")

        click.echo("Running Firecrawl parity comparison...")
        results = asyncio.run(
            run_parity_comparison(
                output_dir, urls=urls, max_urls=max_urls, no_cache=no_cache, cache_only=cache_only
            )
        )

        # Generate reports
        json_path = output_dir / "parity-report.json"
        markdown_path = output_dir / "parity-report.md"

        generate_json_report(results, json_path)
        generate_markdown_report(results, markdown_path)

        click.echo("Parity comparison complete!")
        click.echo(f"JSON report: {json_path}")
        click.echo(f"Markdown report: {markdown_path}")
        click.echo("")
        click.echo(f"Firecrawl provider: {results.get('firecrawl_provider', 'none')}")
        click.echo(f"Recommendation: {results['decision']['recommendation']}")
        click.echo(f"Reason: {results['decision']['reason']}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


@app.command("list-fixes", hidden=True, help="[Dev] List all registered markdown fix plugins.")
def list_fixes() -> None:
    """
    List all registered markdown fix plugins.

    This is a development command for inspecting available fixes.
    It is hidden from the main help output.

    Shows each fix's name, description, issue pattern, and upstream issue.
    Fixes are controlled via site configuration YAML files.
    """
    try:
        index = get_fix_index()
        if not index:
            click.echo("No markdown fixes registered.")
            return

        click.echo("Markdown Fix Plugins")
        click.echo("=" * 80)
        click.echo()

        for i, fix in enumerate(index, 1):
            click.echo(f"{i}. {fix['name']}")
            click.echo(f"   Description: {fix['description']}")
            click.echo(f"   Upstream Issue: {fix['upstream_issue']}")
            if fix.get('min_crawl4ai_version'):
                click.echo(f"   Auto-disable at Crawl4AI: {fix['min_crawl4ai_version']}")
            click.echo()

        click.echo("Configuration:")
        click.echo("  Fixes are disabled by default and must be enabled in site YAML:")
        click.echo("  markdown_fixes:")
        click.echo("    enabled: true")
        click.echo("    fixes:")
        click.echo("      missing-link-text-in-lists: true")
        click.echo()
        click.echo("See docs/40-usage/markdown-fixes.md and sites/template.yaml for more information.")
    except Exception as e:
        click.echo(f"Error listing fixes: {e}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    app()
