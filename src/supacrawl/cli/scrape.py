"""Scraping commands."""

from pathlib import Path

import click

from supacrawl.cli._common import app


@app.command("scrape", help="Scrape a single URL to markdown.")
@click.argument("url")
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    type=click.Choice(
        ["markdown", "html", "rawHtml", "links", "images", "screenshot", "pdf", "json", "branding", "summary"],
        case_sensitive=False,
    ),
    default=["markdown"],
    show_default=True,
    help="Output formats to include",
)
@click.option(
    "--schema",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to JSON schema file (for json format)",
)
@click.option(
    "--prompt",
    "-p",
    type=str,
    default=None,
    help="Extraction prompt (for json format)",
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
    help="Output file. Use .md, .json, .html, .png (screenshot), or .pdf.",
)
@click.option(
    "--full-page/--no-full-page",
    default=True,
    show_default=True,
    help="Capture full scrollable page for screenshots",
)
@click.option(
    "--actions",
    "-a",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to JSON file containing page actions.",
)
@click.option(
    "--include-tags",
    multiple=True,
    help="CSS selectors for elements to include (can be repeated). Takes precedence over --only-main-content.",
)
@click.option(
    "--exclude-tags",
    multiple=True,
    help="CSS selectors for elements to exclude (can be repeated). Applied before include-tags.",
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
    "--max-age",
    type=int,
    default=0,
    show_default=True,
    help="Cache freshness in seconds (0=no cache). Returns cached content if fresh.",
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Cache directory. Defaults to ~/.supacrawl/cache or SUPACRAWL_CACHE_DIR.",
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
    "--solve-captcha/--no-solve-captcha",
    default=False,
    help="Enable CAPTCHA solving via 2Captcha (requires: pip install supacrawl[captcha] and CAPTCHA_API_KEY env var). WARNING: Each solve costs ~$0.002-0.003.",
)
@click.option(
    "--wait-until",
    type=click.Choice(["commit", "domcontentloaded", "load", "networkidle"], case_sensitive=False),
    default=None,
    help="Page load strategy. Default: load. Use 'networkidle' for JS-heavy sites. Also reads SUPACRAWL_WAIT_UNTIL env.",
)
def scrape_url(
    url: str,
    formats: tuple[str, ...],
    schema: Path | None,
    prompt: str | None,
    only_main_content: bool,
    wait_for: int,
    timeout: int,
    output: Path | None,
    full_page: bool,
    actions: Path | None,
    include_tags: tuple[str, ...],
    exclude_tags: tuple[str, ...],
    country: str | None,
    language: str | None,
    timezone: str | None,
    max_age: int,
    cache_dir: Path | None,
    stealth: bool,
    proxy: str | None,
    solve_captcha: bool,
    wait_until: str | None,
) -> None:
    """Scrape a single URL and extract content.

    ANTI-BOT PROTECTION (automatic, no configuration needed):
        Basic fingerprint evasion, browser headers, and bot detection are always active.
        If blocked, automatically retries with enhanced stealth when patchright is installed.

    FOR HEAVILY PROTECTED SITES:
        Install: pip install supacrawl[stealth]
        Then use: --stealth flag

    FOR SITES WITH CAPTCHA:
        1. Install: pip install supacrawl[captcha]
        2. Configure: export CAPTCHA_API_KEY=your-2captcha-api-key
        3. Use: --solve-captcha flag
        WARNING: Each CAPTCHA solve costs ~$0.002-0.003

    Actions JSON format:
        [
            {"type": "wait", "milliseconds": 2000},
            {"type": "click", "selector": "button#load-more"},
            {"type": "scroll", "direction": "down"},
            {"type": "type", "selector": "input#search", "text": "query"},
            {"type": "press", "key": "Enter"},
            {"type": "executeJavascript", "script": "document.title"}
        ]

    Examples:
        supacrawl scrape https://example.com
        supacrawl scrape https://example.com --output page.md
        supacrawl scrape https://example.com --output page.json
        supacrawl scrape https://example.com --format markdown --format html
        supacrawl scrape https://example.com --format images --output images.json
        supacrawl scrape https://example.com --format markdown --format images
        supacrawl scrape https://example.com --format branding --output branding.json
        supacrawl scrape https://example.com --format summary --output summary.txt
        supacrawl scrape https://example.com --format markdown --format summary
        supacrawl scrape https://example.com --format screenshot --output page.png
        supacrawl scrape https://example.com --format pdf --output page.pdf
        supacrawl scrape https://example.com --format json --prompt "Extract product name and price"
        supacrawl scrape https://example.com --format json --schema schema.json
        supacrawl scrape https://example.com --actions actions.json
        supacrawl scrape https://example.com --include-tags article --include-tags .post-content
        supacrawl scrape https://example.com --exclude-tags nav --exclude-tags .sidebar --exclude-tags footer
        supacrawl scrape https://example.com --country AU
        supacrawl scrape https://example.com --language en-AU --timezone Australia/Sydney
        supacrawl scrape https://example.com --max-age 3600  # Use cache if fresh within 1 hour
        supacrawl scrape https://example.com --max-age 3600 --cache-dir ~/.my-cache
        supacrawl scrape https://protected-site.com --stealth  # Force stealth mode
        supacrawl scrape https://captcha-site.com --stealth --solve-captcha  # Solve CAPTCHAs
        supacrawl scrape https://spa-site.com --wait-until networkidle  # Wait for JS to finish
    """
    import asyncio
    import base64
    import json

    from supacrawl.services.scrape import ScrapeService

    # Auto-add format based on output extension if not explicitly provided
    formats_list = list(formats)
    if output:
        suffix = output.suffix.lower()
        if suffix == ".png" and "screenshot" not in formats_list:
            formats_list.append("screenshot")
        elif suffix == ".pdf" and "pdf" not in formats_list:
            formats_list.append("pdf")

    # Parse actions from JSON file if provided
    parsed_actions = None
    if actions:
        from supacrawl.services.actions import parse_actions

        with open(actions) as f:
            actions_json = json.load(f)
        parsed_actions = parse_actions(actions_json)
        click.echo(f"Loaded {len(parsed_actions)} actions from {actions}", err=True)

    # Parse schema from JSON file if provided
    parsed_schema = None
    if schema:
        with open(schema) as f:
            parsed_schema = json.load(f)

    # Validate json format usage
    if "json" in formats_list:
        if not prompt and not parsed_schema:
            click.echo("Error: --prompt or --schema required when using json format", err=True)
            raise SystemExit(1)

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

    # Resolve cache directory if max_age is set
    resolved_cache_dir = cache_dir if max_age > 0 else None
    if max_age > 0 and not resolved_cache_dir:
        # Use default cache dir when max_age is set but no explicit cache_dir
        from supacrawl.cache import CacheManager

        resolved_cache_dir = CacheManager.DEFAULT_CACHE_DIR

    # Print cost warning for CAPTCHA solving
    if solve_captcha:
        click.echo(
            "WARNING: CAPTCHA solving is enabled. Each solve costs ~$0.002-0.003.",
            err=True,
        )

    async def run():
        service = ScrapeService(
            locale_config=locale_config,
            cache_dir=resolved_cache_dir,
            stealth=stealth,
            proxy=proxy,
            solve_captcha=solve_captcha,
        )
        result = await service.scrape(
            url=url,
            formats=formats_list,  # type: ignore[arg-type]
            only_main_content=only_main_content,
            wait_for=wait_for,
            timeout=timeout,
            screenshot_full_page=full_page,
            actions=parsed_actions,
            json_schema=parsed_schema,
            json_prompt=prompt,
            include_tags=list(include_tags) if include_tags else None,
            exclude_tags=list(exclude_tags) if exclude_tags else None,
            max_age=max_age,
            wait_until=wait_until,  # type: ignore[arg-type]
        )
        return result

    result = asyncio.run(run())

    # Handle errors
    if not result.success:
        click.echo(f"Error: {result.error}", err=True)
        raise SystemExit(1)

    # Output handling
    if output:
        suffix = output.suffix.lower()
        if suffix == ".json":
            # Full JSON result
            with open(output, "w") as f:
                json.dump(result.model_dump(exclude_none=True), f, indent=2)
        elif suffix == ".html":
            # HTML content
            if result.data and result.data.html:
                with open(output, "w") as f:
                    f.write(result.data.html)
            else:
                click.echo("No HTML content available", err=True)
                raise SystemExit(1)
        elif suffix == ".png":
            # Screenshot (binary)
            if result.data and result.data.screenshot:
                with open(output, "wb") as fb:
                    fb.write(base64.b64decode(result.data.screenshot))
            else:
                click.echo("No screenshot available", err=True)
                raise SystemExit(1)
        elif suffix == ".pdf":
            # PDF (binary)
            if result.data and result.data.pdf:
                with open(output, "wb") as fb:
                    fb.write(base64.b64decode(result.data.pdf))
            else:
                click.echo("No PDF available", err=True)
                raise SystemExit(1)
        elif suffix == ".txt" and "summary" in formats_list:
            # Summary text only
            if result.data and result.data.summary:
                with open(output, "w") as f:
                    f.write(result.data.summary)
            else:
                click.echo("No summary available", err=True)
                raise SystemExit(1)
        else:
            # Default to markdown (.md or any other extension)
            if result.data and result.data.markdown:
                with open(output, "w") as f:
                    # Add YAML frontmatter with metadata
                    frontmatter = result.data.metadata.to_frontmatter(url)
                    f.write(frontmatter)
                    f.write("\n\n")
                    f.write(result.data.markdown)
            else:
                click.echo("No markdown content available", err=True)
                raise SystemExit(1)
        click.echo(f"Wrote {output}")
    else:
        # Print markdown to stdout
        if result.data and result.data.markdown:
            click.echo(result.data.markdown)
        else:
            click.echo("No markdown content available", err=True)
            raise SystemExit(1)
