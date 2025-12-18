"""Tests for corpus snapshot writing and chunking."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from web_scraper.corpus.writer import write_snapshot
from web_scraper.models import Page, SiteConfig
from web_scraper.prep.chunker import chunk_snapshot


def test_write_snapshot_and_chunk(tmp_path: Path) -> None:
    """Write snapshot then chunk it into JSONL."""
    site = SiteConfig(
        id="example",
        name="Example",
        entrypoints=["https://example.com"],
        include=["https://example.com"],
        exclude=[],
        max_pages=2,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
    )
    pages = [
        Page(
            site_id="example",
            url="https://example.com",
            title="Home",
            path="/index",
            content_markdown="Hello world",
            content_hash="hash-home",
            provider="crawl4ai",
        )
    ]

    snapshot_path = asyncio.run(write_snapshot(site, pages, tmp_path))
    chunks_path = asyncio.run(chunk_snapshot(snapshot_path, max_chars=20))

    manifest = json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["site_id"] == "example"
    assert manifest["total_pages"] == 1

    lines = chunks_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    records = [json.loads(line) for line in lines]
    assert records[0]["page_url"] == "https://example.com"
    assert any("Hello world" in record["text"] for record in records)
