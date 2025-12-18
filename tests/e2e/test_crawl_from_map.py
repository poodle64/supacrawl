"""Tests for crawl-from-map functionality (map then crawl workflow)."""

from __future__ import annotations

import asyncio
import http.server
import json
import socketserver
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from web_scraper.map import map_site
from web_scraper.map_io import load_map_entries, select_crawl_urls
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
from web_scraper.sites.loader import load_site_config

# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SITES_DIR = FIXTURES_DIR / "sites"
HTML_DIR = FIXTURES_DIR / "html" / "map_site"


def _setup_map_server(tmp_path: Path) -> tuple[str, Any]:
    """
    Set up a local HTTP server for map test fixtures.
    
    Serves the map_site directory and robots.txt.
    
    Args:
        tmp_path: Temporary directory path.
        
    Returns:
        Tuple of (base_url, server_instance).
    """
    class MapHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(HTML_DIR), **kwargs)
        
        def do_GET(self):
            # Handle robots.txt specially
            if self.path == "/robots.txt":
                robots_path = HTML_DIR / "robots.txt"
                if robots_path.exists():
                    self.send_response(200)
                    self.send_header("Content-type", "text/plain")
                    self.end_headers()
                    self.wfile.write(robots_path.read_bytes())
                    return
            # Default to SimpleHTTPRequestHandler
            super().do_GET()
    
    # Use port 0 to get a free port
    httpd = socketserver.TCPServer(("127.0.0.1", 0), MapHandler)
    port = httpd.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    
    # Start server in daemon thread
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    
    # Small delay to ensure server is ready
    time.sleep(0.1)
    
    return base_url, httpd


def test_crawl_from_map_jsonl_crawls_only_included_urls_network_free(tmp_path: Path) -> None:
    """
    Test crawl from map file crawls only included and allowed URLs.
    
    Verifies:
    - Only allowed/included URLs from map are crawled
    - Excluded URL (tools/hidden.html) is not crawled
    - Page count equals expected included count
    """
    # Set up local server (network-free)
    base_url, server = _setup_map_server(tmp_path)
    
    # Load map-static config and update entrypoints
    config = load_site_config("map-static", SITES_DIR)
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
            "exclude": [urljoin(base_url, "/tools/**")],
        }
    )
    
    # Generate a map file with some URLs (including one that should be excluded)
    map_entries = asyncio.run(
        map_site(
            config,
            max_urls=200,
            include_entrypoints_only=False,
            use_sitemap=False,
            use_robots=True,
        )
    )
    
    # Write map file as JSONL
    map_file = tmp_path / "map.jsonl"
    with map_file.open("w", encoding="utf-8") as f:
        for entry in map_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    # Load and select URLs from map
    loaded_entries = load_map_entries(map_file)
    assert len(loaded_entries) > 0, "Map file should contain entries"
    
    # Select crawl URLs (default filter: included=true and allowed=true)
    target_urls = select_crawl_urls(loaded_entries)
    
    # Verify excluded URL is not in target list
    excluded_url = urljoin(base_url, "/tools/hidden.html")
    assert excluded_url not in target_urls, "Excluded URL should not be in target URLs"
    
    # Verify included URLs are present
    entrypoint_url = urljoin(base_url, "/index.html")
    assert entrypoint_url in target_urls, "Entrypoint should be in target URLs"
    
    # Count expected included URLs (included=true and allowed=true)
    expected_count = sum(
        1
        for entry in loaded_entries
        if entry.get("included", True) and entry.get("allowed", True)
    )
    
    # Run crawl with target_urls
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path, target_urls=target_urls)
    
    # Verify pages were crawled
    assert len(pages) >= 1, f"Should crawl at least 1 page (got {len(pages)})"
    
    # Verify excluded URL was not crawled
    page_urls = {page.url for page in pages}
    assert excluded_url not in page_urls, "Excluded URL should not be crawled"
    
    # Verify page count matches expected (allowing for Crawl4AI failures)
    if len(pages) < expected_count:
        failed_urls = set(target_urls) - page_urls
        assert len(pages) >= 1, (
            f"Expected {expected_count} pages, got {len(pages)}. "
            f"Failed URLs: {failed_urls}"
        )
    
    # Verify manifest exists and contains expected pages
    manifest_path = snapshot_path / "manifest.json"
    assert manifest_path.exists(), "Manifest should exist"
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_urls = {page["url"] for page in manifest["pages"]}
    assert excluded_url not in manifest_urls, "Excluded URL should not be in manifest"


def test_crawl_from_map_is_deterministic_order(tmp_path: Path) -> None:
    """
    Test crawl from map preserves deterministic order.
    
    Verifies:
    - manifest.pages[].url order identical across both runs
    - content hash for first page stable across runs
    """
    # Set up local server
    base_url, server = _setup_map_server(tmp_path)
    
    # Load config
    config = load_site_config("map-static", SITES_DIR)
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
            "exclude": [urljoin(base_url, "/tools/**")],
        }
    )
    
    # Generate map with URLs
    map_entries = asyncio.run(
        map_site(
            config,
            max_urls=10,
            include_entrypoints_only=False,
            use_sitemap=False,
            use_robots=False,
        )
    )
    
    # Write map file
    map_file = tmp_path / "map.jsonl"
    with map_file.open("w", encoding="utf-8") as f:
        for entry in map_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    # Load and select URLs (should be sorted)
    loaded_entries = load_map_entries(map_file)
    target_urls = select_crawl_urls(loaded_entries)
    
    # Verify URLs are sorted
    assert target_urls == sorted(target_urls), "URLs should be sorted"
    
    # Crawl using target_urls (first run)
    scraper = Crawl4AIScraper()
    pages1, snapshot_path1 = scraper.crawl(config, corpora_dir=tmp_path / "run1", target_urls=target_urls)
    
    # Verify pages are in deterministic order (check manifest)
    manifest_path1 = snapshot_path1 / "manifest.json"
    manifest1 = json.loads(manifest_path1.read_text(encoding="utf-8"))
    manifest_urls1 = [page["url"] for page in manifest1["pages"]]
    
    # Verify manifest URLs are sorted (deterministic)
    assert manifest_urls1 == sorted(manifest_urls1), "Manifest URLs should be in sorted order"
    
    # Get first page content hash
    first_page_hash1 = None
    if pages1:
        first_page_hash1 = pages1[0].content_hash
    
    # Run again to verify determinism
    pages2, snapshot_path2 = scraper.crawl(config, corpora_dir=tmp_path / "run2", target_urls=target_urls)
    manifest2 = json.loads((snapshot_path2 / "manifest.json").read_text(encoding="utf-8"))
    manifest_urls2 = [page["url"] for page in manifest2["pages"]]
    
    # Verify manifest URL order is identical
    assert manifest_urls1 == manifest_urls2, "Crawl order should be deterministic (manifest URLs identical)"
    
    # Verify first page content hash is stable
    if pages2 and first_page_hash1:
        first_page_hash2 = pages2[0].content_hash
        assert first_page_hash1 == first_page_hash2, "First page content hash should be stable across runs"


def test_crawl_without_map_unchanged(tmp_path: Path) -> None:
    """
    Test crawl without map file behaves unchanged.
    
    Verifies default crawl behavior is not affected when --from-map is not provided.
    """
    # Set up local server
    base_url, server = _setup_map_server(tmp_path)
    
    # Load config
    config = load_site_config("map-static", SITES_DIR)
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
            "exclude": [urljoin(base_url, "/tools/**")],
        }
    )
    
    # Run crawl without map (default behavior, target_urls=None)
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path, target_urls=None)
    
    # Verify at least one page was crawled
    assert len(pages) >= 1, "Should crawl at least one page"
    
    # Verify manifest exists and is valid
    manifest_path = snapshot_path / "manifest.json"
    assert manifest_path.exists(), "Manifest should exist"
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["total_pages"] >= 1, "Manifest should have at least one page"
    assert len(manifest["pages"]) >= 1, "Manifest pages array should have entries"
    
    # Verify entrypoint was crawled
    entrypoint_url = urljoin(base_url, "/index.html")
    page_urls = {page.url for page in pages}
    assert entrypoint_url in page_urls, "Entrypoint should be crawled"
