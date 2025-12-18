"""Test multi-format output integrity (Firecrawl-style verification).

This test suite verifies that all requested output formats are correctly
written to disk and properly referenced in the manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin

from tests.helpers.server import setup_static_server
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
from web_scraper.sites.loader import load_site_config

# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SITES_DIR = FIXTURES_DIR / "sites"




def test_all_formats_written_to_disk(tmp_path: Path) -> None:
    """
    Verify all requested formats are written to disk with correct extensions.
    
    Args:
        tmp_path: Temporary directory for test output.
    """
    # Set up local server (network-free)
    base_url, server = setup_static_server(tmp_path)
    
    # Load baseline-static config and override formats
    config = load_site_config("baseline-static", SITES_DIR)
    requested_formats = ["markdown", "html", "json", "text"]
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
            "formats": requested_formats,
        }
    )
    
    # Run crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Verify at least one page was crawled
    assert len(pages) > 0, "No pages crawled"
    
    # Verify format directories exist
    for fmt in requested_formats:
        format_dir = snapshot_path / fmt
        assert format_dir.exists(), f"Format directory {fmt}/ does not exist"
        assert format_dir.is_dir(), f"{fmt}/ is not a directory"
    
    # Verify files exist for each format
    format_extensions = {
        "markdown": ".md",
        "html": ".html",
        "json": ".json",
        "text": ".txt",
    }
    
    for fmt in requested_formats:
        format_dir = snapshot_path / fmt
        # Find all files with correct extension
        files = list(format_dir.rglob(f"*{format_extensions[fmt]}"))
        assert len(files) > 0, f"No {fmt} files found in {format_dir}"
        # Verify all files have correct extension
        for file_path in files:
            assert file_path.suffix == format_extensions[fmt], (
                f"File {file_path} has wrong extension for format {fmt}"
            )


def test_manifest_formats_integrity(tmp_path: Path) -> None:
    """
    Verify manifest correctly references all formats per page.
    
    Args:
        tmp_path: Temporary directory for test output.
    """
    # Set up local server (network-free)
    base_url, server = setup_static_server(tmp_path)
    
    # Load baseline-static config and override formats
    config = load_site_config("baseline-static", SITES_DIR)
    requested_formats = ["markdown", "html", "json", "text"]
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
            "formats": requested_formats,
        }
    )
    
    # Run crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Load manifest
    manifest_path = snapshot_path / "manifest.json"
    assert manifest_path.exists(), "Manifest file does not exist"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Verify top-level formats array
    assert "formats" in manifest, "Manifest missing 'formats' field"
    manifest_formats = manifest["formats"]
    assert isinstance(manifest_formats, list), "Manifest 'formats' must be a list"
    assert set(manifest_formats) == set(requested_formats), (
        f"Manifest formats {manifest_formats} do not match requested {requested_formats}"
    )
    
    # Verify pages array exists
    assert "pages" in manifest, "Manifest missing 'pages' field"
    manifest_pages = manifest["pages"]
    assert len(manifest_pages) > 0, "Manifest has no pages"
    
    # Verify each page has formats dict
    for page_entry in manifest_pages:
        assert "formats" in page_entry, f"Page {page_entry.get('url')} missing 'formats' field"
        page_formats = page_entry["formats"]
        assert isinstance(page_formats, dict), f"Page {page_entry.get('url')} 'formats' must be a dict"
        
        # Verify all requested formats are present
        assert set(page_formats.keys()) == set(requested_formats), (
            f"Page {page_entry.get('url')} formats {list(page_formats.keys())} "
            f"do not match requested {requested_formats}"
        )
        
        # Verify each format path exists on disk
        for fmt, rel_path in page_formats.items():
            file_path = snapshot_path / rel_path
            assert file_path.exists(), (
                f"Page {page_entry.get('url')} format {fmt} path {rel_path} does not exist on disk"
            )
            assert file_path.is_file(), (
                f"Page {page_entry.get('url')} format {fmt} path {rel_path} is not a file"
            )
        
        # Verify primary path matches first format
        assert "path" in page_entry, f"Page {page_entry.get('url')} missing 'path' field"
        primary_path = page_entry["path"]
        first_format_path = page_formats[requested_formats[0]]
        assert primary_path == first_format_path, (
            f"Page {page_entry.get('url')} primary path {primary_path} "
            f"does not match first format path {first_format_path}"
        )


def test_cross_format_naming_consistency(tmp_path: Path) -> None:
    """
    Verify cross-format file naming consistency (same dir_path/filename, only extension differs).
    
    Args:
        tmp_path: Temporary directory for test output.
    """
    # Set up local server (network-free)
    base_url, server = setup_static_server(tmp_path)
    
    # Load baseline-static config and override formats
    config = load_site_config("baseline-static", SITES_DIR)
    requested_formats = ["markdown", "html", "json", "text"]
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
            "formats": requested_formats,
        }
    )
    
    # Run crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Load manifest
    manifest_path = snapshot_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # Verify cross-format consistency for each page
    for page_entry in manifest["pages"]:
        page_formats = page_entry["formats"]
        
        # Extract dir_path and filename stem for each format
        format_paths = {}
        for fmt, rel_path in page_formats.items():
            full_path = snapshot_path / rel_path
            format_paths[fmt] = {
                "dir_path": full_path.parent.relative_to(snapshot_path / fmt),
                "filename_stem": full_path.stem,
                "extension": full_path.suffix,
            }
        
        # Verify all formats share the same dir_path (relative to format directory)
        dir_paths = {fmt: info["dir_path"] for fmt, info in format_paths.items()}
        unique_dir_paths = set(dir_paths.values())
        assert len(unique_dir_paths) == 1, (
            f"Page {page_entry.get('url')} has inconsistent dir_paths across formats: {dir_paths}"
        )
        
        # Verify all formats share the same filename stem
        filename_stems = {fmt: info["filename_stem"] for fmt, info in format_paths.items()}
        unique_stems = set(filename_stems.values())
        assert len(unique_stems) == 1, (
            f"Page {page_entry.get('url')} has inconsistent filename stems across formats: {filename_stems}"
        )
        
        # Verify extensions differ (as expected)
        extensions = {fmt: info["extension"] for fmt, info in format_paths.items()}
        expected_extensions = {
            "markdown": ".md",
            "html": ".html",
            "json": ".json",
            "text": ".txt",
        }
        for fmt, ext in extensions.items():
            assert ext == expected_extensions[fmt], (
                f"Page {page_entry.get('url')} format {fmt} has wrong extension: {ext} "
                f"(expected {expected_extensions[fmt]})"
            )
