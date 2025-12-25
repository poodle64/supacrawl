"""CLI end-to-end smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from supacrawl.cli import app
from supacrawl.corpus.writer import SCHEMA_VERSION


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
