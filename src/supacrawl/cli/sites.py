"""Site configuration management commands."""

from __future__ import annotations

from pathlib import Path

import click

from supacrawl.cli._common import app
from supacrawl.config import default_sites_dir
from supacrawl.exceptions import SupacrawlError
from supacrawl.sites.loader import list_site_configs, load_site_config



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
    except SupacrawlError as exc:
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
    from supacrawl.init import scaffold_site_config

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
