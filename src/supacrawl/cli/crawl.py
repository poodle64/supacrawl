"""Crawl commands for website scraping."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from supacrawl.cli._common import app, configure_logging
from supacrawl.config import default_corpora_dir, default_sites_dir
from supacrawl.exceptions import SupacrawlError
from supacrawl.prep.chunker import chunk_snapshot
from supacrawl.sites.loader import load_site_config




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
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    type=click.Choice(["markdown", "html", "json"], case_sensitive=False),
    default=["markdown"],
    show_default=True,
    help="Output formats to save",
)
@click.option(
    "--deduplicate-similar-urls",
    is_flag=True,
    default=False,
    help="Deduplicate URLs that differ only by tracking parameters or fragments",
)
@click.option(
    "--allow-external-links",
    is_flag=True,
    default=False,
    help="Follow and scrape links to external domains (Firecrawl-compatible)",
)
@click.option(
    "--country",
    type=str,
    default=None,
    help="ISO country code for locale settings (e.g., AU, US, DE). Sets language and timezone defaults.",
)
@click.option(
    "--language",
    type=str,
    default=None,
    help="Browser language/locale code (e.g., en-AU, de-DE). Overrides --country language.",
)
@click.option(
    "--timezone",
    type=str,
    default=None,
    help="IANA timezone (e.g., Australia/Sydney). Overrides --country timezone.",
)
@click.option(
    "--stealth/--no-stealth",
    default=False,
    help="Enhanced stealth mode via Patchright (requires: pip install supacrawl[stealth]). Note: Basic anti-bot evasion is always active.",
)
@click.option(
    "--proxy",
    type=str,
    default=None,
    help="Proxy URL (e.g., http://user:pass@host:port, socks5://host:port). Also reads SUPACRAWL_PROXY env.",
)
def crawl_url(
    url: str,
    limit: int,
    depth: int,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    output: Path,
    resume: bool,
    formats: tuple[str, ...],
    deduplicate_similar_urls: bool,
    allow_external_links: bool,
    country: str | None,
    language: str | None,
    timezone: str | None,
    stealth: bool,
    proxy: str | None,
) -> None:
    """Crawl a website and save all pages (Firecrawl-compatible).

    Examples:
        supacrawl crawl-url https://example.com --limit 50 --output corpus/
        supacrawl crawl-url https://example.com --output corpus/ --format markdown --format html
        supacrawl crawl-url https://example.com --output corpus/ --resume
        supacrawl crawl-url https://example.com --output corpus/ --deduplicate-similar-urls
        supacrawl crawl-url https://example.com --output corpus/ --allow-external-links --limit 50
        supacrawl crawl-url https://example.com --output corpus/ --country AU
    """
    import asyncio

    from supacrawl.services.crawl import CrawlService

    # Build locale config if any location options specified
    locale_config = None
    if country or language or timezone:
        from supacrawl.models import LocaleConfig

        if country:
            locale_config = LocaleConfig.from_country(country)
            # Override with explicit language/timezone if provided
            if language:
                locale_config = locale_config.model_copy(update={"language": language})
            if timezone:
                locale_config = locale_config.model_copy(update={"timezone": timezone})
        else:
            locale_config = LocaleConfig(language=language, timezone=timezone)

    async def run():
        from urllib.parse import urlparse

        service = CrawlService()

        click.echo(f"Crawling {url}...", err=True)

        async for event in service.crawl(
            url=url,
            limit=limit,
            max_depth=depth,
            include_patterns=list(include) if include else None,
            exclude_patterns=list(exclude) if exclude else None,
            output_dir=output,
            resume=resume,
            formats=list(formats),
            deduplicate_similar_urls=deduplicate_similar_urls,
            allow_external_links=allow_external_links,
            locale_config=locale_config,
            stealth=stealth,
            proxy=proxy,
        ):
            if event.type == "progress":
                # Show progress bar
                if event.total and event.total > 0:
                    pct = int((event.completed / event.total) * 100)
                    bar_width = 25
                    filled = int(bar_width * event.completed / event.total)
                    bar = "=" * filled + ">" + " " * (bar_width - filled - 1)
                    click.echo(
                        f"\r[{bar}] {event.completed}/{event.total} pages ({pct}%)",
                        nl=False,
                        err=True,
                    )
            elif event.type == "page":
                # Extract path from URL for cleaner output
                path = urlparse(event.url).path or "/"
                click.echo(f"\n  + {path}")
            elif event.type == "error":
                path = urlparse(event.url).path if event.url else "unknown"
                error_msg = event.error or "unknown error"
                # Extract status code if present
                if "404" in error_msg:
                    click.echo(f"\n  x {path} (404)", err=True)
                else:
                    click.echo(f"\n  x {path} ({error_msg})", err=True)
            elif event.type == "complete":
                click.echo(
                    f"\n\nComplete: {event.completed}/{event.total} pages", err=True
                )

    asyncio.run(run())

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
# Provider option removed - now always uses Playwright
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

    Raises:
        click.ClickException: If the site configuration is not found or invalid.
    """
    from supacrawl.corpus.state import (
        find_resumable_snapshot,
        load_state,
    )

    configure_logging(verbose)
    sites_dir = default_sites_dir(base_path)
    corpora_dir = default_corpora_dir(base_path)

    # Handle URL quick-start: if site_name looks like a URL, require --init
    if site_name.startswith("http://") or site_name.startswith("https://"):
        if not init:
            click.echo(
                "Error: When using a URL as the first argument, you must provide --init <site_name>",
                err=True,
            )
            click.echo(
                "Example: supacrawl crawl https://example.com --init my-site",
                err=True,
            )
            raise SystemExit(1)

        # Create site config from URL
        from supacrawl.init import scaffold_site_config

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
    except SupacrawlError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
        raise SystemExit(1) from exc

    # Handle dry-run mode
    if dry_run:
        from supacrawl.map import map_site as map_site_func

        try:
            url_entries = asyncio.run(map_site_func(config, max_urls=config.max_pages))
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
        from supacrawl.map_io import load_map_entries, select_crawl_urls

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
            from supacrawl.models import OutputFormat

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
    resume = not fresh
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
        else:
            click.echo(f"Starting crawl for {config.name}...")
    else:
        # Check if there was an incomplete snapshot we're ignoring
        assert config.id is not None, "config.id must be set after validation"
        incomplete = find_resumable_snapshot(corpora_dir, config.id)
        if incomplete:
            click.echo(f"Starting fresh crawl for {config.name}...")
        else:
            click.echo(f"Starting crawl for {config.name}...")

    # Use CrawlService with CorpusOutputAdapter for unified scraping pipeline
    from supacrawl.corpus.adapter import CorpusOutputAdapter
    from supacrawl.services.crawl import CrawlService

    # Build include/exclude patterns from config
    include_patterns = list(config.include) if config.include else None
    exclude_patterns = list(config.exclude) if config.exclude else None

    # If target_urls provided (from map file), use first URL as starting point
    start_url = target_urls[0] if target_urls else config.entrypoints[0]

    # Create output adapter for corpus output with manifests
    output_adapter = CorpusOutputAdapter(
        site_config=config,
        corpora_dir=corpora_dir,
        resume=resume,
    )

    async def run_crawl():
        from urllib.parse import urlparse

        service = CrawlService()
        pages_scraped = 0
        snapshot_path = None

        async for event in service.crawl(
            url=start_url,
            limit=config.max_pages,
            max_depth=3,  # Default depth for site crawl
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            output_adapter=output_adapter,
        ):
            if event.type == "progress":
                # Show progress bar
                if event.total and event.total > 0:
                    pct = int((event.completed / event.total) * 100)
                    bar_width = 25
                    filled = int(bar_width * event.completed / event.total)
                    bar = "=" * filled + ">" + " " * (bar_width - filled - 1)
                    click.echo(
                        f"\r[{bar}] {event.completed}/{event.total} pages ({pct}%)",
                        nl=False,
                        err=True,
                    )
            elif event.type == "page":
                # Extract path from URL for cleaner output
                path = urlparse(event.url).path or "/"
                if verbose:
                    click.echo(f"\n  + {path}")
                pages_scraped = event.completed or pages_scraped
            elif event.type == "error":
                if event.url:
                    path = urlparse(event.url).path
                    error_msg = event.error or "unknown error"
                    click.echo(f"\n  x {path} ({error_msg})", err=True)
                else:
                    click.echo(f"\nError: {event.error}", err=True)
            elif event.type == "complete":
                click.echo(
                    f"\n\nComplete: {event.completed}/{event.total} pages", err=True
                )
                pages_scraped = event.completed or pages_scraped
                snapshot_path = output_adapter.snapshot_path

        return pages_scraped, snapshot_path

    try:
        pages_count, snapshot_path = asyncio.run(run_crawl())

        # Generate chunks if requested
        chunk_count = 0
        if chunks and snapshot_path:
            chunks_path = asyncio.run(
                chunk_snapshot(snapshot_path, max_chars=max_chars)
            )
            # Count chunks
            chunk_count = sum(1 for _ in chunks_path.read_text().splitlines())

        # Output summary
        assert config.id is not None, "config.id must be set after validation"
        if chunks:
            click.echo(f"Crawled {pages_count} pages, generated {chunk_count} chunks")
        else:
            click.echo(f"Crawled {pages_count} pages")

        # Show output path - use relative path if base_path not provided, else show from base
        if base_path is None:
            click.echo(f"Output: corpora/{config.id}/latest/")
        else:
            click.echo(f"Output: {base_path}/corpora/{config.id}/latest/")
        if verbose and snapshot_path:
            click.echo(f"Snapshot ID: {snapshot_path.name}")
    except KeyboardInterrupt:
        # Handle Ctrl+C at CLI level as fallback
        click.echo("\nCrawl interrupted.", err=True)
        raise SystemExit(130)  # Standard exit code for SIGINT
    except Exception as exc:
        # Check for CrawlInterrupted (graceful shutdown with saved state)
        from supacrawl.exceptions import CrawlInterrupted

        if isinstance(exc, CrawlInterrupted):
            click.echo(
                f"\nCrawl interrupted. Progress saved: {exc.pages_completed} pages.",
                err=True,
            )
            click.echo(f"Resume: supacrawl crawl {site_name}", err=True)
            raise SystemExit(130)
        raise
