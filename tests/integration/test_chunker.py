"""Tests for chunking behaviour."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from web_scraper.exceptions import FileNotFoundError
from web_scraper.corpus.writer import SCHEMA_VERSION
from web_scraper.prep.chunker import chunk_snapshot


def _write_manifest(snapshot_path: Path, pages: list[dict]) -> None:
    """Helper to create a manifest file with required metadata."""
    snapshot_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "site_id": "site",
        "site_name": "Test Site",
        "snapshot_id": "snap",
        "created_at": "2025-01-01T00:00:00Z",
        "provider": "crawl4ai",
        "entrypoints": ["https://example.com"],
        "total_pages": len(pages),
        "formats": ["markdown"],
        "pages": pages,
        "correlation_id": "test123",
        "metadata": {
            "snapshot_id": "snap",
            "site_id": "site",
            "created_at": "2025-01-01T00:00:00Z",
            "git_commit": None,
            "site_config_hash": "a" * 64,  # Dummy hash
            "crawl_engine": "crawl4ai",
            "crawl_engine_version": None,
            "schema_version": SCHEMA_VERSION,
        },
    }
    (snapshot_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_chunk_snapshot_missing_manifest_raises(tmp_path: Path) -> None:
    """Chunking without a manifest raises FileNotFoundError."""
    snapshot_path = tmp_path / "site" / "snap"

    with pytest.raises(FileNotFoundError):
        asyncio.run(chunk_snapshot(snapshot_path))


def test_chunk_snapshot_splits_on_paragraphs(tmp_path: Path) -> None:
    """Chunking respects max_chars and preserves order."""
    snapshot_path = tmp_path / "site" / "snap"
    markdown_dir = snapshot_path / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    page_rel = Path("markdown/page.md")
    page_text = "Alpha paragraph\n\nBeta paragraph that is longer"
    (markdown_dir / "page.md").write_text(page_text, encoding="utf-8")

    _write_manifest(
        snapshot_path,
        [
            {
                "url": "https://example.com/page",
                "title": "Example",
                "path": str(page_rel),
            }
        ],
    )

    chunks_path = asyncio.run(chunk_snapshot(snapshot_path, max_chars=20))

    lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["chunk_index"] == 0
    assert second["chunk_index"] == 1
    assert first["text"].startswith("Alpha")
    assert "Beta" in second["text"]


def test_chunk_snapshot_empty_pages_handles_gracefully(tmp_path: Path) -> None:
    """Chunking snapshot with empty pages list should create empty chunks file."""
    snapshot_path = tmp_path / "site" / "snap"
    snapshot_path.mkdir(parents=True, exist_ok=True)

    _write_manifest(snapshot_path, [])

    chunks_path = asyncio.run(chunk_snapshot(snapshot_path))

    assert chunks_path.exists()
    lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 0


def test_chunk_snapshot_preserves_metadata(tmp_path: Path) -> None:
    """Chunking should preserve page metadata in chunk records."""
    snapshot_path = tmp_path / "site" / "snap"
    markdown_dir = snapshot_path / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    page_rel = Path("markdown/page.md")
    (markdown_dir / "page.md").write_text("Test content", encoding="utf-8")

    _write_manifest(
        snapshot_path,
        [
            {
                "url": "https://example.com/page",
                "title": "Test Page",
                "path": str(page_rel),
            }
        ],
    )

    chunks_path = asyncio.run(chunk_snapshot(snapshot_path))

    lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    chunk = json.loads(lines[0])
    assert chunk["page_url"] == "https://example.com/page"
    assert chunk["page_title"] == "Test Page"
    assert "chunk_index" in chunk
    assert "text" in chunk
