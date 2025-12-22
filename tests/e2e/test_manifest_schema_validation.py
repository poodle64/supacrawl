"""Tests for manifest JSON schema validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web_scraper.scrapers.playwright_scraper import PlaywrightScraper
from web_scraper.models import SiteConfig


def test_manifest_validates_against_schema(tmp_path: Path) -> None:
    """
    Test that generated manifest.json validates against snapshot-manifest.schema.json.
    
    Uses existing local static fixture to avoid network.
    """
    try:
        from jsonschema import validate, ValidationError
    except ImportError:
        pytest.skip("jsonschema package not available (install with: pip install jsonschema)")
    
    from tests.helpers.server import setup_static_server
    
    # Set up local HTTP server
    base_url, server = setup_static_server(tmp_path)
    
    # Load baseline-static config
    config = SiteConfig.model_validate({
        "id": "test-schema",
        "name": "Test Schema",
        "entrypoints": [f"{base_url}/index.html"],
        "include": [f"{base_url}/**"],
        "exclude": [],
        "max_pages": 1,
        "formats": ["markdown"],
        "only_main_content": True,
        "include_subdomains": False,
    })
    
    # Run a crawl
    scraper = PlaywrightScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Load manifest
    manifest_path = snapshot_path / "manifest.json"
    assert manifest_path.exists(), "Manifest should exist"
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Load schema (at project root)
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "snapshot-manifest.schema.json"
    assert schema_path.exists(), f"Schema file should exist at {schema_path}"
    
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    
    # Validate manifest against schema
    try:
        validate(instance=manifest, schema=schema)
    except ValidationError as e:
        pytest.fail(
            f"Manifest does not validate against schema:\n"
            f"Path: {'.'.join(str(p) for p in e.absolute_path)}\n"
            f"Message: {e.message}\n"
            f"Manifest keys: {list(manifest.keys())}\n"
            f"Metadata keys: {list(manifest.get('metadata', {}).keys())}"
        )


def test_manifest_schema_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    """
    Test that schema validation fails when manifest contains unknown top-level fields.
    """
    try:
        from jsonschema import validate, ValidationError
    except ImportError:
        pytest.skip("jsonschema package not available (install with: pip install jsonschema)")
    
    from tests.helpers.server import setup_static_server
    
    # Set up local HTTP server
    base_url, server = setup_static_server(tmp_path)
    
    # Load baseline-static config
    config = SiteConfig.model_validate({
        "id": "test-schema-strict",
        "name": "Test Schema Strict",
        "entrypoints": [f"{base_url}/index.html"],
        "include": [f"{base_url}/**"],
        "exclude": [],
        "max_pages": 1,
        "formats": ["markdown"],
        "only_main_content": True,
        "include_subdomains": False,
    })
    
    # Run a crawl
    scraper = PlaywrightScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Load manifest
    manifest_path = snapshot_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Load schema (at project root)
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "snapshot-manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    
    # Inject unknown top-level field
    manifest_with_unknown = manifest.copy()
    manifest_with_unknown["unknown_field"] = "should_fail"
    
    # Validate should fail
    with pytest.raises(ValidationError) as exc_info:
        validate(instance=manifest_with_unknown, schema=schema)
    
    # Assert error mentions additional properties
    assert "additional" in exc_info.value.message.lower() or "unknown" in exc_info.value.message.lower()
