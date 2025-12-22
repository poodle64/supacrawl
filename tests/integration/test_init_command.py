"""Integration tests for init command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from web_scraper.cli import app
from web_scraper.sites.loader import load_site_config


def test_init_creates_valid_config_with_url(tmp_path: Path) -> None:
    """Init command with --url should create a valid site config."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "test-site", "--url", "https://example.com", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code == 0
    assert "Created" in result.output
    
    # Verify config file exists
    config_path = tmp_path / "sites" / "test-site.yaml"
    assert config_path.exists()
    
    # Verify config is valid by loading it
    config = load_site_config("test-site", tmp_path / "sites")
    assert config.name == "Test Site"  # Derived from site_name
    assert config.entrypoints == ["https://example.com"]
    assert "https://example.com/**" in config.include
    assert config.max_pages == 100  # Default
    assert config.formats == ["markdown"]


def test_init_fails_when_config_exists(tmp_path: Path) -> None:
    """Init command should fail if config already exists."""
    # Create initial config
    runner = CliRunner()
    result1 = runner.invoke(
        app,
        ["init", "test-site", "--url", "https://example.com", "--base-path", str(tmp_path)],
    )
    assert result1.exit_code == 0
    
    # Try to create again
    result2 = runner.invoke(
        app,
        ["init", "test-site", "--url", "https://example.com", "--base-path", str(tmp_path)],
    )
    
    assert result2.exit_code != 0
    assert "already exists" in result2.output


def test_init_derives_include_pattern_from_url(tmp_path: Path) -> None:
    """Init should derive include pattern from URL path."""
    runner = CliRunner()
    
    # Test with path in URL
    result = runner.invoke(
        app,
        ["init", "docs-site", "--url", "https://example.com/docs", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code == 0
    
    config = load_site_config("docs-site", tmp_path / "sites")
    assert "https://example.com/docs/**" in config.include


def test_init_handles_url_with_trailing_slash(tmp_path: Path) -> None:
    """Init should handle URLs with trailing slashes."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "test-site", "--url", "https://example.com/docs/", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code == 0
    
    config = load_site_config("test-site", tmp_path / "sites")
    # Trailing slash should be stripped
    assert "https://example.com/docs/**" in config.include


def test_init_creates_sites_directory_if_missing(tmp_path: Path) -> None:
    """Init should create sites/ directory if it doesn't exist."""
    # Don't pre-create sites directory
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "test-site", "--url", "https://example.com", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code == 0
    assert (tmp_path / "sites").exists()
    assert (tmp_path / "sites" / "test-site.yaml").exists()


def test_init_generates_display_name_from_site_name(tmp_path: Path) -> None:
    """Init should generate display name from site_name."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "my-awesome-site", "--url", "https://example.com", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code == 0
    
    config = load_site_config("my-awesome-site", tmp_path / "sites")
    # Hyphens replaced with spaces, title case
    assert config.name == "My Awesome Site"


def test_init_without_url_fails_in_non_interactive_mode(tmp_path: Path) -> None:
    """Init without --url should fail when not in interactive mode."""
    runner = CliRunner()
    # CliRunner runs in non-interactive mode by default
    result = runner.invoke(
        app,
        ["init", "test-site", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code != 0
    assert "--url is required" in result.output or "URL is required" in result.output


def test_crawl_with_url_and_init_creates_config_and_crawls(monkeypatch, tmp_path: Path) -> None:
    """Crawl with URL and --init should create config and perform crawl."""
    from tests.integration.test_cli import FakeScraper
    
    monkeypatch.setattr("web_scraper.cli.PlaywrightScraper", FakeScraper)
    
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "https://example.com", "--init", "test-site", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code == 0
    
    # Verify config was created
    config_path = tmp_path / "sites" / "test-site.yaml"
    assert config_path.exists()
    
    # Verify config is valid
    config = load_site_config("test-site", tmp_path / "sites")
    assert config.entrypoints == ["https://example.com"]
    
    # Verify crawl happened (snapshot created)
    corpora_dir = tmp_path / "corpora" / "test-site"
    assert corpora_dir.exists()
    snapshots = [d for d in corpora_dir.iterdir() if d.is_dir() and d.name != "latest"]
    assert len(snapshots) >= 1, "Crawl should have created a snapshot"


def test_crawl_with_url_without_init_fails(tmp_path: Path) -> None:
    """Crawl with URL but no --init should fail with clear error."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "https://example.com", "--base-path", str(tmp_path)],
    )
    
    assert result.exit_code != 0
    assert "--init" in result.output
    assert "Example:" in result.output or "example" in result.output.lower()

