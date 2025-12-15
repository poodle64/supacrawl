"""Tests for map command (URL discovery without crawling)."""

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

import pytest

from web_scraper.map import map_site
from web_scraper.sites.loader import load_site_config

# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
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


def test_map_jsonl_outputs_expected_urls_without_network(tmp_path: Path) -> None:
    """
    Test map command outputs expected URLs with correct filtering.
    
    Verifies:
    - Includes index, docs/page1
    - Excludes docs/page2 (robots.txt)
    - Excludes tools/hidden (exclude pattern)
    - Excludes external link
    - Output is stable and sorted
    - Correct reasons set
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
    
    # Run map
    url_entries = asyncio.run(
        map_site(
            config,
            max_urls=200,
            include_entrypoints_only=False,
            use_sitemap=False,
            use_robots=True,
        )
    )
    
    # Convert to dict for easier lookup
    url_dict = {entry["url"]: entry for entry in url_entries}
    
    # Verify entrypoint is included
    entrypoint_url = urljoin(base_url, "/index.html")
    assert entrypoint_url in url_dict, "Entrypoint should be included"
    entrypoint_entry = url_dict[entrypoint_url]
    assert entrypoint_entry["source"] == "entrypoint"
    assert entrypoint_entry["depth"] == 0
    assert entrypoint_entry["included"] is True
    assert entrypoint_entry["excluded_reason"] is None
    
    # Verify docs/page1 is included (from HTML links)
    page1_url = urljoin(base_url, "/docs/page1.html")
    assert page1_url in url_dict, "docs/page1.html should be included"
    page1_entry = url_dict[page1_url]
    assert page1_entry["source"] == "html_links"
    assert page1_entry["depth"] == 1
    assert page1_entry["included"] is True
    assert page1_entry["excluded_reason"] is None
    
    # Verify docs/page2 is excluded (robots.txt)
    page2_url = urljoin(base_url, "/docs/page2.html")
    if page2_url in url_dict:
        # If it appears, it should be marked as excluded
        page2_entry = url_dict[page2_url]
        assert page2_entry["excluded_reason"] == "robots_disallow"
        assert page2_entry["included"] is False
    # It may not appear at all if filtered early
    
    # Verify tools/hidden is excluded (exclude pattern)
    hidden_url = urljoin(base_url, "/tools/hidden.html")
    if hidden_url in url_dict:
        hidden_entry = url_dict[hidden_url]
        assert hidden_entry["excluded_reason"] == "exclude_pattern"
        assert hidden_entry["included"] is False
    
    # Verify external link is not included (different domain)
    external_url = "https://external.example/"
    assert external_url not in url_dict, "External link should not be included"
    
    # Verify output is sorted
    urls = [entry["url"] for entry in url_entries]
    assert urls == sorted(urls), "URLs should be sorted"
    
    # Verify no duplicates
    assert len(urls) == len(set(urls)), "No duplicate URLs"


def test_map_entrypoints_only_mode(tmp_path: Path) -> None:
    """
    Test map with --include-entrypoints-only flag.
    
    Verifies only entrypoints are returned.
    """
    # Set up local server
    base_url, server = _setup_map_server(tmp_path)
    
    # Load config
    config = load_site_config("map-static", SITES_DIR)
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
        }
    )
    
    # Run map with entrypoints only
    url_entries = asyncio.run(
        map_site(
            config,
            max_urls=200,
            include_entrypoints_only=True,
            use_sitemap=False,
            use_robots=False,
        )
    )
    
    # Should only have entrypoint
    assert len(url_entries) == 1, "Should only return entrypoint"
    assert url_entries[0]["source"] == "entrypoint"
    assert url_entries[0]["depth"] == 0
    assert url_entries[0]["url"] == urljoin(base_url, "/index.html")


def test_map_max_urls_cap(tmp_path: Path) -> None:
    """
    Test map respects max-urls limit.
    
    Verifies output length is capped and deterministic.
    """
    # Set up local server
    base_url, server = _setup_map_server(tmp_path)
    
    # Load config
    config = load_site_config("map-static", SITES_DIR)
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
        }
    )
    
    # Run map with max_urls=1
    url_entries = asyncio.run(
        map_site(
            config,
            max_urls=1,
            include_entrypoints_only=False,
            use_sitemap=False,
            use_robots=False,
        )
    )
    
    # Should have exactly 1 URL
    assert len(url_entries) == 1, "Should respect max_urls=1"
    
    # Should be deterministic (entrypoint first)
    assert url_entries[0]["source"] == "entrypoint"
    assert url_entries[0]["url"] == urljoin(base_url, "/index.html")
    
    # Run again to verify determinism
    url_entries2 = asyncio.run(
        map_site(
            config,
            max_urls=1,
            include_entrypoints_only=False,
            use_sitemap=False,
            use_robots=False,
        )
    )
    
    assert url_entries == url_entries2, "Output should be deterministic"
