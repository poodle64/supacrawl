"""Integration tests for --chunks flag on crawl command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from web_scraper.cli import app
from tests.integration.test_cli import FakeScraper, _write_site_config


def test_crawl_with_chunks_produces_chunks_file(monkeypatch, tmp_path: Path) -> None:
    """Crawl with --chunks flag should produce chunks.jsonl."""
    _write_site_config(tmp_path)

    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)

    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--chunks", "--base-path", str(tmp_path)]
    )

    assert result.exit_code == 0
    
    # Check chunks file exists
    latest = tmp_path / "corpora" / "example" / "latest"
    chunks_path = latest / "chunks.jsonl"
    assert chunks_path.exists() or latest.resolve().joinpath("chunks.jsonl").exists()


def test_crawl_without_chunks_no_chunks_file(monkeypatch, tmp_path: Path) -> None:
    """Crawl without --chunks flag should not produce chunks.jsonl."""
    _write_site_config(tmp_path)

    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)

    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--base-path", str(tmp_path)]
    )

    assert result.exit_code == 0
    
    # Check chunks file does NOT exist
    site_dir = tmp_path / "corpora" / "example"
    snapshots = [d for d in site_dir.iterdir() if d.is_dir() and d.name != "latest"]
    if snapshots:
        chunks_path = snapshots[0] / "chunks.jsonl"
        assert not chunks_path.exists()

