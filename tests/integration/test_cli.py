"""CLI end-to-end smoke tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import override

from click.testing import CliRunner

from web_scraper.cli import app
from web_scraper.corpus.layout import new_snapshot_id, snapshot_root
from web_scraper.corpus.writer import SCHEMA_VERSION
from web_scraper.models import Page, SiteConfig
from web_scraper.scrapers.base import Scraper


class FakeScraper(Scraper):
    """Minimal scraper that returns a single page."""

    provider_name = "fake"

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        """Accept any kwargs for compatibility with Crawl4AIScraper signature."""
        pass

    @override
    def crawl(
        self,
        config: SiteConfig,
        corpora_dir: Path | None = None,
        resume_snapshot: Path | None = None,
        target_urls: list[str] | None = None,
    ) -> tuple[list[Page], Path]:
        """Fake crawl implementation for testing."""
        base_dir = corpora_dir or Path.cwd() / "corpora"
        snapshot_id = new_snapshot_id()
        snapshot_path = snapshot_root(config.id, base_dir, snapshot_id)
        snapshot_path.mkdir(parents=True, exist_ok=True)

        # Use target_urls if provided, otherwise use entrypoints
        urls_to_use = target_urls if target_urls else config.entrypoints
        first_url = urls_to_use[0] if urls_to_use else config.entrypoints[0]

        pages = [
            Page(
                site_id=config.id,
                url=first_url,
                title="Home",
                path="/index",
                content_markdown="Hello world",
                content_hash="hash",
                provider=self.provider_name,
            )
        ]

        # Write the page markdown file using new format-based structure
        # Root URL (https://example.com) -> markdown/index.md
        markdown_dir = snapshot_path / "markdown"
        markdown_dir.mkdir(parents=True, exist_ok=True)
        page_file = markdown_dir / "index.md"
        page_file.write_text(pages[0].content_markdown, encoding="utf-8")

        # Write manifest
        import json as json_module

        manifest = {
            "site_id": config.id,
            "site_name": config.name,
            "provider": self.provider_name,
            "snapshot_id": snapshot_id,
            "created_at": snapshot_id,
            "entrypoints": config.entrypoints,
            "total_pages": len(pages),
            "formats": config.formats,
            "pages": [
                {
                    "url": p.url,
                    "title": p.title,
                    "path": str(page_file.relative_to(snapshot_path)),
                    "content_hash": p.content_hash,
                    "formats": {"markdown": str(page_file.relative_to(snapshot_path))},
                }
                for p in pages
            ],
            "correlation_id": "test",
            "metadata": {
                "snapshot_id": snapshot_id,
                "site_id": config.id,
                "created_at": "2025-01-01T00:00:00Z",
                "git_commit": None,
                "site_config_hash": "a" * 64,
                "crawl_engine": "crawl4ai",
                "crawl_engine_version": None,
                "schema_version": SCHEMA_VERSION,
            },
        }
        manifest_path = snapshot_path / "manifest.json"
        manifest_path.write_text(
            json_module.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Create latest symlink (simulating what writer.complete() does)
        from web_scraper.corpus.symlink import update_latest_symlink
        site_dir = snapshot_path.parent
        update_latest_symlink(site_dir, snapshot_id)

        return pages, snapshot_path


def _write_site_config(base_path: Path) -> None:
    sites_dir = base_path / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)
    (sites_dir / "example.yaml").write_text(
        "id: example\n"
        "name: Example\n"
        "entrypoints:\n"
        "  - https://example.com\n"
        "include:\n"
        "  - https://example.com\n"
        "exclude: []\n"
        "max_pages: 1\n"
        "formats:\n"
        "  - markdown\n"
        "only_main_content: true\n"
        "include_subdomains: false\n",
        encoding="utf-8",
    )


def test_cli_crawl_and_chunk_end_to_end(monkeypatch, tmp_path: Path) -> None:
    """Crawl then chunk via CLI using a fake scraper."""
    base_path = tmp_path
    _write_site_config(base_path)
    corpora_dir = base_path / "corpora"

    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)

    runner = CliRunner()
    crawl_result = runner.invoke(
        app, ["crawl", "example", "--base-path", str(base_path)]
    )

    assert crawl_result.exit_code == 0
    site_dir = corpora_dir / "example"
    snapshots = [d for d in site_dir.iterdir() if d.is_dir() and d.name != "latest"]
    assert len(snapshots) == 1
    snapshot_id = snapshots[0].name

    chunk_result = runner.invoke(
        app,
        [
            "chunk",
            "example",
            snapshot_id,
            "--base-path",
            str(base_path),
            "--max-chars",
            "10",
        ],
    )

    assert chunk_result.exit_code == 0
    chunks_path = snapshots[0] / "chunks.jsonl"
    lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    record = json.loads(lines[0])
    assert record["page_url"] == "https://example.com"
    assert record["chunk_index"] == 0


def test_cli_chunk_missing_snapshot_shows_error(tmp_path: Path) -> None:
    """Chunk command should fail when snapshot is absent."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "chunk",
            "missing-site",
            "missing-snapshot",
            "--base-path",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "Snapshot not found" in result.output


def test_cli_list_sites_command(tmp_path: Path) -> None:
    """List-sites command should list available site configurations."""
    _write_site_config(tmp_path)
    sites_dir = tmp_path / "sites"
    (sites_dir / "another.yaml").write_text(
        "id: another\n"
        "name: Another\n"
        "entrypoints:\n"
        "  - https://another.com\n"
        "include:\n"
        "  - https://another.com\n"
        "exclude: []\n"
        "max_pages: 10\n"
        "formats:\n"
        "  - html\n"
        "only_main_content: true\n"
        "include_subdomains: false\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["list-sites", "--base-path", str(tmp_path)])

    assert result.exit_code == 0
    assert "example" in result.output
    assert "another" in result.output


def test_cli_list_sites_empty_directory(tmp_path: Path) -> None:
    """List-sites command should handle empty sites directory."""
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)

    runner = CliRunner()
    result = runner.invoke(app, ["list-sites", "--base-path", str(tmp_path)])

    assert result.exit_code == 0
    assert "No site configurations found" in result.output


def test_cli_show_site_command(tmp_path: Path) -> None:
    """Show-site command should display site configuration details."""
    _write_site_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["show-site", "example", "--base-path", str(tmp_path)])

    assert result.exit_code == 0
    assert "ID: example" in result.output
    assert "Name: Example" in result.output
    assert "https://example.com" in result.output
    assert "Max pages: 1" in result.output


def test_cli_show_site_missing_config_shows_error(tmp_path: Path) -> None:
    """Show-site command should show error when config is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["show-site", "missing", "--base-path", str(tmp_path)])

    assert result.exit_code != 0
    assert "Error:" in result.output
    assert "correlation_id=" in result.output


def test_cli_crawl_invalid_config_shows_error(tmp_path: Path) -> None:
    """Crawl command should show error when config is invalid."""
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)
    (sites_dir / "invalid.yaml").write_text(
        "id: invalid\nentrypoints: []\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["crawl", "invalid", "--base-path", str(tmp_path)])

    assert result.exit_code != 0
    assert "Error:" in result.output
    assert "correlation_id=" in result.output


def test_cli_crawl_creates_latest_symlink(monkeypatch, tmp_path: Path) -> None:
    """Crawl command should create a 'latest' symlink."""
    base_path = tmp_path
    _write_site_config(base_path)

    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)

    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--base-path", str(base_path)]
    )

    assert result.exit_code == 0
    
    # Check symlink exists
    latest_symlink = base_path / "corpora" / "example" / "latest"
    assert latest_symlink.is_symlink()
    
    # Check symlink resolves to a valid snapshot
    resolved = latest_symlink.resolve()
    assert resolved.is_dir()
    assert (resolved / "manifest.json").exists()


def test_cli_crawl_dry_run_shows_urls_without_snapshot(tmp_path: Path) -> None:
    """Crawl with --dry-run should show URLs without creating snapshot."""
    base_path = tmp_path
    _write_site_config(base_path)

    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--dry-run", "--base-path", str(base_path)]
    )

    assert result.exit_code == 0
    
    # Check output contains URLs
    assert "https://example.com" in result.output
    
    # Check output contains summary
    assert "URLs would be crawled" in result.output
    
    # Check no snapshot was created
    corpora_dir = base_path / "corpora"
    if corpora_dir.exists():
        site_dir = corpora_dir / "example"
        if site_dir.exists():
            snapshots = [d for d in site_dir.iterdir() if d.is_dir() and d.name != "latest"]
            assert len(snapshots) == 0, "No snapshots should be created in dry-run mode"
