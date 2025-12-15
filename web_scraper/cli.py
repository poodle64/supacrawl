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
def map_site(
    site_name: str,
    base_path: Path | None,
    max_urls: int,
    format: str,
    output: Path | None,
    use_sitemap: bool | None,
    use_robots: bool | None,
    include_entrypoints_only: bool,
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
@click.option(
    "--from-map",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Crawl only the URLs in a map output file (json or jsonl).",
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
    from_map: Path | None,
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
        from_map: Path to JSON or JSONL map file. If provided, crawl only URLs from map.

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
    if target_urls:
        click.echo(f"Starting crawl: {config.id} ({site_name}) with {len(target_urls)} URLs from map...")
    else:
        click.echo(f"Starting crawl: {config.id} ({site_name}) with {len(config.entrypoints)} entrypoints...")

    pages, snapshot_path = scraper.crawl(
        config,
        corpora_dir,
        resume_snapshot=resume_snapshot,
        target_urls=target_urls,
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


@app.command("parity", help="Run Firecrawl parity comparison harness.")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path("parity-reports"),
    help="Directory for parity report output.",
)
def parity(output_dir: Path) -> None:
    """
    Run Firecrawl parity comparison to evaluate fixes subsystem.

    Compares web-scraper output (baseline-static vs enhanced) against Firecrawl
    to make evidence-based decision on whether fixes subsystem should be kept.

    Requires FIRECRAWL_API_KEY environment variable for Firecrawl comparisons.
    """
    import asyncio

    from web_scraper.parity.harness import run_parity_comparison
    from web_scraper.parity.report import generate_json_report, generate_markdown_report

    try:
        click.echo("Running Firecrawl parity comparison...")
        results = asyncio.run(run_parity_comparison(output_dir))

        # Generate reports
        json_path = output_dir / "parity-report.json"
        markdown_path = output_dir / "parity-report.md"

        generate_json_report(results, json_path)
        generate_markdown_report(results, markdown_path)

        click.echo("Parity comparison complete!")
        click.echo(f"JSON report: {json_path}")
        click.echo(f"Markdown report: {markdown_path}")
        click.echo("")
        click.echo(f"Recommendation: {results['decision']['recommendation']}")
        click.echo(f"Reason: {results['decision']['reason']}")
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
