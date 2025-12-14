"""Command-line interface for web-scraper."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import logging

import click

from web_scraper.config import default_corpora_dir, default_sites_dir
from web_scraper.content.fixes.index import get_fix_index
from web_scraper.corpus.compress import compress_snapshot, extract_archive
from web_scraper.discovery import discover_sitemaps, parse_sitemap, filter_urls_by_patterns
from web_scraper.prep.chunker import chunk_snapshot
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
from web_scraper.sites.loader import list_site_configs, load_site_config
from web_scraper.exceptions import WebScrapeError


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


@app.command("map", help="Discover URLs from sitemap without crawling.")
@click.argument("site_name")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ folder.",
)
@click.option(
    "--sitemap-url",
    type=str,
    default=None,
    help="Explicit sitemap URL to use (overrides auto-discovery).",
)
@click.option(
    "--max-urls",
    type=int,
    default=1000,
    show_default=True,
    help="Maximum number of URLs to display.",
)
def map_site(
    site_name: str,
    base_path: Path | None,
    sitemap_url: str | None,
    max_urls: int,
) -> None:
    """
    Discover URLs from a site's sitemap.

    Shows all URLs that would be crawled based on sitemap discovery
    and the site's include/exclude patterns.

    Args:
        site_name: Name of the site configuration (without .yaml extension).
        base_path: Optional base directory containing sites/ folder.
        sitemap_url: Explicit sitemap URL to use.
        max_urls: Maximum URLs to display.
    """
    sites_dir = default_sites_dir(base_path)

    try:
        config = load_site_config(site_name, sites_dir)
    except WebScrapeError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
        raise SystemExit(1) from exc

    # Determine sitemap URL to use
    if sitemap_url:
        sitemap_urls = [sitemap_url]
    elif config.sitemap.urls:
        sitemap_urls = config.sitemap.urls
    else:
        # Auto-discover from first entrypoint
        if not config.entrypoints:
            click.echo("Error: No entrypoints configured for auto-discovery.", err=True)
            raise SystemExit(1)
        click.echo(f"Discovering sitemaps from {config.entrypoints[0]}...")
        sitemap_urls = asyncio.run(discover_sitemaps(config.entrypoints[0]))

    if not sitemap_urls:
        click.echo("No sitemaps found. Try specifying --sitemap-url explicitly.")
        raise SystemExit(1)

    click.echo(f"Found {len(sitemap_urls)} sitemap(s)")
    for sm_url in sitemap_urls:
        click.echo(f"  - {sm_url}")

    # Parse all sitemaps
    all_urls = []
    for sm_url in sitemap_urls:
        click.echo(f"\nParsing {sm_url}...")
        urls = asyncio.run(parse_sitemap(sm_url, max_urls=max_urls))
        all_urls.extend(urls)
        click.echo(f"  Found {len(urls)} URLs")

    # Filter by include/exclude patterns
    filtered = filter_urls_by_patterns(
        all_urls, config.include, config.exclude
    )

    click.echo("\n=== URL Summary ===")
    click.echo(f"Total URLs in sitemap: {len(all_urls)}")
    click.echo(f"URLs matching include/exclude: {len(filtered)}")
    click.echo(f"Config max_pages: {config.max_pages}")

    if len(filtered) > config.max_pages:
        click.echo(
            f"\nWarning: {len(filtered)} URLs exceed max_pages ({config.max_pages})"
        )

    click.echo(f"\n=== URLs ({min(len(filtered), max_urls)} shown) ===")
    for i, url in enumerate(filtered[:max_urls]):
        lastmod_str = f" (lastmod: {url.lastmod.date()})" if url.lastmod else ""
        click.echo(f"{i+1:4d}. {url.loc}{lastmod_str}")


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
    "--resume",
    type=str,
    default=None,
    help="Resume an existing crawl. Pass snapshot ID or 'latest' for most recent.",
)
@click.option(
    "--rps",
    type=float,
    default=None,
    help="Override requests-per-second rate limit.",
)
@click.option(
    "--delay",
    type=float,
    default=None,
    help="Override per-domain delay (seconds).",
)
@click.option(
    "--pool-size",
    type=int,
    default=None,
    help="Browser pool size (default: from config or 3).",
)
@click.option(
    "--proxy",
    type=str,
    multiple=True,
    help="Proxy URL(s) to use. Can be specified multiple times.",
)
@click.option(
    "--formats",
    type=str,
    default=None,
    help="Comma-separated output formats (markdown, html, text, json). Overrides config.",
)
def crawl(
    site_name: str,
    base_path: Path | None,
    verbose: bool,
    resume: str | None,
    rps: float | None,
    delay: float | None,
    pool_size: int | None,
    proxy: tuple[str, ...],
    formats: str | None,
) -> None:
    """
    Crawl a site and write a snapshot.

    Args:
        site_name: Name of the site configuration (without .yaml extension).
        base_path: Optional base directory containing sites/ and corpora/ folders.
        verbose: Show detailed progress logs.
        resume: Snapshot ID to resume, or 'latest'.
        rps: Override requests-per-second.
        delay: Override per-domain delay.
        pool_size: Browser pool size.
        proxy: Proxy URLs to use.
        formats: Comma-separated output formats.

    Raises:
        click.ClickException: If the site configuration is not found or invalid.
    """
    from web_scraper.corpus.state import (
        find_latest_snapshot,
        find_resumable_snapshot,
        load_state,
    )
    from web_scraper.rate_limit import RateLimitConfig, RateLimiter
    from web_scraper.browser.pool import BrowserPool, BrowserPoolConfig
    from web_scraper.network.proxy import ProxyRotator, ProxyConfig, Proxy

    _configure_logging(verbose)
    sites_dir = default_sites_dir(base_path)
    corpora_dir = default_corpora_dir(base_path)

    try:
        config = load_site_config(site_name, sites_dir)
    except WebScrapeError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
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

    # Handle resume option
    resume_snapshot: Path | None = None
    if resume:
        if resume == "latest":
            resume_snapshot = find_resumable_snapshot(corpora_dir, config.id)
            if not resume_snapshot:
                # Try latest even if completed
                resume_snapshot = find_latest_snapshot(corpora_dir, config.id)
        else:
            resume_snapshot = corpora_dir / config.id / resume

        if resume_snapshot and resume_snapshot.exists():
            state = load_state(resume_snapshot)
            if state:
                if state.status == "completed":
                    click.echo(
                        f"Warning: Snapshot {resume_snapshot.name} is already completed. "
                        "Starting fresh crawl instead.",
                        err=True,
                    )
                    resume_snapshot = None
                else:
                    click.echo(
                        f"Resuming crawl from {resume_snapshot.name}: "
                        f"{state.checkpoint_page} pages completed, "
                        f"{len(state.pending_urls)} pending, "
                        f"{len(state.failed_urls)} failed"
                    )
        elif resume_snapshot:
            click.echo(f"Warning: Snapshot {resume} not found. Starting fresh crawl.", err=True)
            resume_snapshot = None

    # Build rate limiter
    rate_config = RateLimitConfig(
        requests_per_second=rps or config.rate_limit.requests_per_second,
        per_domain_delay=delay or config.rate_limit.per_domain_delay,
        max_concurrent=config.rate_limit.max_concurrent,
        respect_crawl_delay=config.rate_limit.respect_crawl_delay,
        adaptive=config.rate_limit.adaptive,
    )
    rate_limiter = RateLimiter(rate_config)
    if verbose:
        click.echo(
            f"Rate limiting: {rate_config.requests_per_second} RPS, "
            f"{rate_config.per_domain_delay}s domain delay, "
            f"max {rate_config.max_concurrent} concurrent"
        )

    # Build browser pool (if enabled)
    browser_pool: BrowserPool | None = None
    if config.browser_pool.enabled:
        pool_config = BrowserPoolConfig(
            pool_size=pool_size or config.browser_pool.pool_size,
            max_pages_per_browser=config.browser_pool.max_pages_per_browser,
            restart_on_crash=config.browser_pool.restart_on_crash,
        )
        browser_pool = BrowserPool(config=pool_config)
        if verbose:
            click.echo(f"Browser pool: {pool_config.pool_size} browsers")

    # Build proxy rotator (if configured)
    proxy_rotator: ProxyRotator | None = None
    if proxy or config.proxy.enabled:
        proxy_list = list(proxy) if proxy else config.proxy.proxies
        if proxy_list:
            proxy_config = ProxyConfig(
                enabled=True,
                proxies=[Proxy.from_url(p) for p in proxy_list],
                min_success_rate=config.proxy.min_success_rate,
                fallback_direct=config.proxy.fallback_direct,
            )
            proxy_rotator = ProxyRotator(proxy_config)
            if verbose:
                click.echo(f"Proxy rotation: {len(proxy_list)} proxies")

    scraper = Crawl4AIScraper(
        rate_limiter=rate_limiter,
        browser_pool=browser_pool,
        proxy_rotator=proxy_rotator,
    )
    click.echo(f"Starting crawl: {config.id} ({site_name}) with {len(config.entrypoints)} entrypoints...")

    pages, snapshot_path = scraper.crawl(
        config,
        corpora_dir,
        resume_snapshot=resume_snapshot,
    )

    click.echo(f"Finished crawl: {config.id} -> {len(pages)} pages")
    click.echo(f"Snapshot created at {snapshot_path}")

    # Show rate limit stats if verbose
    if verbose:
        stats = rate_limiter.stats
        click.echo(
            f"Rate limiting: {stats['total_requests']} requests, "
            f"{stats['total_wait_time']:.1f}s total wait, "
            f"{stats['rate_limit_hits']} 429 responses"
        )


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
        click.echo(f"Chunks written to {output_path}")
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


@app.command("list-fixes", help="List all registered markdown fix plugins and their status.")
def list_fixes() -> None:
    """
    List all registered markdown fix plugins.

    Shows each fix's name, description, issue pattern, and upstream issue.
    Fixes are controlled via site configuration YAML files.
    """
    try:
        # Import fixes to ensure they're registered
        from web_scraper.content.fixes import missing_link_text  # noqa: F401

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
            click.echo(f"   Issue Pattern: {fix['issue_pattern']}")
            click.echo(f"   Upstream Issue: {fix['upstream_issue']}")
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
