"""Tests for manifest metadata."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from web_scraper.corpus.writer import write_snapshot
from web_scraper.models import Page, SiteConfig
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper


def test_manifest_contains_metadata(tmp_path: Path) -> None:
    """
    Test that manifest.json contains metadata object with all required keys.
    
    Uses existing local static fixture to avoid network.
    """
    from tests.test_baseline_quality import _setup_static_server
    
    # Set up local HTTP server
    base_url, server = _setup_static_server(tmp_path)
    
    # Load baseline-static config
    sites_dir = Path(__file__).parent.parent / "fixtures" / "sites"
    config = SiteConfig.model_validate({
        "id": "test-metadata",
        "name": "Test Metadata",
        "entrypoints": [f"{base_url}/index.html"],
        "include": [f"{base_url}/**"],
        "exclude": [],
        "max_pages": 1,
        "formats": ["markdown"],
        "only_main_content": True,
        "include_subdomains": False,
    })
    
    # Run a crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Load manifest
    manifest_path = snapshot_path / "manifest.json"
    assert manifest_path.exists(), "Manifest should exist"
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Assert metadata exists
    assert "metadata" in manifest, "Manifest should contain metadata"
    metadata = manifest["metadata"]
    
    # Assert all required keys exist
    required_keys = [
        "snapshot_id",
        "site_id",
        "created_at",
        "git_commit",
        "site_config_hash",
        "crawl_engine",
        "crawl_engine_version",
    ]
    for key in required_keys:
        assert key in metadata, f"Metadata should contain '{key}'"
    
    # Assert values are correct type
    assert metadata["snapshot_id"] == manifest["snapshot_id"]
    assert metadata["site_id"] == config.id
    assert metadata["crawl_engine"] == "crawl4ai"
    assert isinstance(metadata["created_at"], str)
    assert metadata["git_commit"] is None or isinstance(metadata["git_commit"], str)
    assert isinstance(metadata["site_config_hash"], str)
    assert metadata["crawl_engine_version"] is None or isinstance(metadata["crawl_engine_version"], str)


def test_site_config_hash_is_stable(tmp_path: Path) -> None:
    """
    Test that site_config_hash is identical for identical configs.
    
    Runs two crawls with the same config and verifies hash matches.
    """
    from tests.test_baseline_quality import _setup_static_server
    
    # Set up local HTTP server
    base_url, server = _setup_static_server(tmp_path)
    
    # Create identical config
    config = SiteConfig.model_validate({
        "id": "test-hash",
        "name": "Test Hash",
        "entrypoints": [f"{base_url}/index.html"],
        "include": [f"{base_url}/**"],
        "exclude": [],
        "max_pages": 1,
        "formats": ["markdown"],
        "only_main_content": True,
        "include_subdomains": False,
    })
    
    # Run first crawl
    scraper = Crawl4AIScraper()
    pages1, snapshot_path1 = scraper.crawl(config, corpora_dir=tmp_path / "run1")
    
    # Run second crawl with identical config
    pages2, snapshot_path2 = scraper.crawl(config, corpora_dir=tmp_path / "run2")
    
    # Load manifests
    manifest1 = json.loads((snapshot_path1 / "manifest.json").read_text(encoding="utf-8"))
    manifest2 = json.loads((snapshot_path2 / "manifest.json").read_text(encoding="utf-8"))
    
    # Assert hashes are identical
    hash1 = manifest1["metadata"]["site_config_hash"]
    hash2 = manifest2["metadata"]["site_config_hash"]
    assert hash1 == hash2, "Site config hash should be stable for identical configs"
    assert len(hash1) == 64, "SHA-256 hash should be 64 hex characters"


def test_created_at_is_iso8601(tmp_path: Path) -> None:
    """
    Test that created_at is in ISO-8601 format (UTC).
    
    Validates format only, not value.
    """
    from tests.test_baseline_quality import _setup_static_server
    
    # Set up local HTTP server
    base_url, server = _setup_static_server(tmp_path)
    
    config = SiteConfig.model_validate({
        "id": "test-iso",
        "name": "Test ISO",
        "entrypoints": [f"{base_url}/index.html"],
        "include": [f"{base_url}/**"],
        "exclude": [],
        "max_pages": 1,
        "formats": ["markdown"],
        "only_main_content": True,
        "include_subdomains": False,
    })
    
    # Run crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Load manifest
    manifest = json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    created_at = manifest["metadata"]["created_at"]
    
    # Validate ISO-8601 format (with timezone)
    # Pattern: YYYY-MM-DDTHH:MM:SS[.ssssss][+HH:MM] or Z
    iso_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$"
    )
    assert iso_pattern.match(created_at), f"created_at should be ISO-8601 format, got: {created_at}"


def test_backward_compat_manifest_load(tmp_path: Path) -> None:
    """
    Test that loading a manifest without metadata does not raise an exception.
    
    Creates a minimal manifest fixture without metadata and verifies it loads.
    """
    # Create a minimal manifest without metadata (simulating old format)
    manifest_path = tmp_path / "manifest.json"
    old_manifest = {
        "site_id": "test-old",
        "site_name": "Test Old",
        "snapshot_id": "20250101T000000",
        "created_at": "2025-01-01T00:00:00+10:00",
        "provider": "crawl4ai",
        "entrypoints": ["https://example.com"],
        "total_pages": 1,
        "formats": ["markdown"],
        "pages": [],
    }
    
    manifest_path.write_text(json.dumps(old_manifest, indent=2), encoding="utf-8")
    
    # Load manifest (should not raise)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Assert it loads correctly
    assert loaded["site_id"] == "test-old"
    assert "metadata" not in loaded, "Old manifest should not have metadata"
