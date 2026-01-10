"""Crawl commands for website scraping."""

from pathlib import Path

import click

from supacrawl.cli._common import app


@app.command("crawl", help="Crawl a website from a starting URL.")
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
    help="Follow and scrape links to external domains.",
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
@click.option(
    "--concurrency",
    "-c",
    type=int,
    default=10,
    show_default=True,
    help="Max concurrent requests for URL processing.",
)
@click.option(
    "--wait-until",
    type=click.Choice(["commit", "domcontentloaded", "load", "networkidle"], case_sensitive=False),
    default=None,
    help="Page load strategy. Default: load. Use 'networkidle' for JS-heavy sites. Also reads SUPACRAWL_WAIT_UNTIL env.",
)
def crawl_cmd(
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
    concurrency: int,
    wait_until: str | None,
) -> None:
    """Crawl a website and save all pages.

    Examples:
        supacrawl crawl https://example.com --limit 50 --output corpus/
        supacrawl crawl https://example.com --output corpus/ --format markdown --format html
        supacrawl crawl https://example.com --output corpus/ --resume
        supacrawl crawl https://example.com --output corpus/ --deduplicate-similar-urls
        supacrawl crawl https://example.com --output corpus/ --allow-external-links --limit 50
        supacrawl crawl https://example.com --output corpus/ --country AU
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
            concurrency=concurrency,
            wait_until=wait_until,  # type: ignore[arg-type]
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
                click.echo(f"\n\nComplete: {event.completed}/{event.total} pages", err=True)

    asyncio.run(run())
