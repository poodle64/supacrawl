"""URL mapping and discovery commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from supacrawl.cli._common import app
from supacrawl.config import default_sites_dir
from supacrawl.exceptions import SupacrawlError
from supacrawl.sites.loader import load_site_config




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
    help="Output file path. If omitted, prints to stdout.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "text"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format: json (full result) or text (URLs only).",
)
@click.option(
    "--ignore-query-params",
    is_flag=True,
    default=False,
    help="Remove query parameters from URLs (Firecrawl-compatible).",
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
def map_url(
    url: str,
    limit: int,
    depth: int,
    sitemap: str,
    include_subdomains: bool,
    search: str | None,
    output: Path | None,
    output_format: str,
    ignore_query_params: bool,
    stealth: bool,
    proxy: str | None,
) -> None:
    """Map a website to discover all URLs (Firecrawl-compatible).

    Examples:
        supacrawl map-url https://example.com
        supacrawl map-url https://example.com --limit 50 --format json
        supacrawl map-url https://example.com --search about --output urls.json --format json
    """
    import asyncio
    import json

    from supacrawl.services.map import MapService

    async def run():
        service = MapService(stealth=stealth, proxy=proxy)
        result = await service.map(
            url=url,
            limit=limit,
            max_depth=depth,
            sitemap=sitemap,  # type: ignore[arg-type]
            include_subdomains=include_subdomains,
            search=search,
            ignore_query_params=ignore_query_params,
        )
        return result

    result = asyncio.run(run())

    # Handle errors
    if not result.success:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    # Generate output content based on format
    if output_format == "json":
        # exclude_none=True matches Firecrawl format (optional fields omitted when None)
        content = json.dumps(result.model_dump(exclude_none=True), indent=2)
    else:
        # Text format: URLs only, one per line
        content = "\n".join(link.url for link in result.links)

    # Write to file or stdout
    if output:
        with open(output, "w") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")
        click.echo(f"Wrote {len(result.links)} URLs to {output}")
    else:
        click.echo(content)

@app.command(
    "map", help="Map site URLs that would be crawled (Firecrawl-style discovery)."
)
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

    from supacrawl.map import map_site as map_site_func

    sites_dir = default_sites_dir(base_path)

    try:
        config = load_site_config(site_name, sites_dir)
    except SupacrawlError as exc:
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
