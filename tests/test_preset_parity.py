"""Parity test comparing enhanced vs pure_crawl4ai markdown quality presets.

This test runs the same crawl twice with different presets and compares
metrics to ensure both presets produce acceptable output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urljoin

import pytest

from tests.helpers.quality_metrics import calculate_all_metrics
from web_scraper.models import SiteConfig
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
from web_scraper.sites.loader import load_site_config

# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SITES_DIR = FIXTURES_DIR / "sites"
PARITY_REPORTS_DIR = FIXTURES_DIR / "parity_reports"


def _setup_static_server(tmp_path: Path) -> tuple[str, Any]:
    """
    Set up a local HTTP server for static HTML fixture.
    
    Args:
        tmp_path: Temporary directory path.
        
    Returns:
        Tuple of (base_url, server_instance).
    """
    import http.server
    import socketserver
    import threading
    import time
    
    html_dir = FIXTURES_DIR / "html"
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(html_dir), **kwargs)
    
    # Use port 0 to get a free port
    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    
    # Start server in daemon thread (will be cleaned up when process exits)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    
    # Small delay to ensure server is ready
    time.sleep(0.1)
    
    return base_url, httpd


def _run_crawl_with_preset(
    config: SiteConfig, preset: str, corpora_dir: Path
) -> tuple[dict[str, object], str]:
    """
    Run crawl with specified preset and return metrics and first page markdown.
    
    Args:
        config: Site configuration.
        preset: Quality preset ("enhanced" or "pure_crawl4ai").
        corpora_dir: Directory for corpus output.
        
    Returns:
        Tuple of (metrics_dict, first_page_markdown).
    """
    # Create preset-specific config
    preset_config = config.model_copy(update={"markdown_quality_preset": preset})
    
    # Run crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(preset_config, corpora_dir=corpora_dir)
    
    # Calculate metrics
    metrics = calculate_all_metrics(pages, snapshot_path)
    
    # Get first page markdown for debugging
    first_page_markdown = pages[0].content_markdown if pages else ""
    
    return metrics, first_page_markdown


def test_preset_parity_baseline_static(tmp_path: Path) -> None:
    """
    Compare enhanced vs pure_crawl4ai presets for baseline-static.
    
    This test runs the same crawl twice with different presets and asserts
    both produce acceptable output without requiring them to match.
    
    Args:
        tmp_path: Temporary directory for test output.
    """
    # Set up local server (network-free)
    base_url, server = _setup_static_server(tmp_path)
    
    # Load baseline-static config
    config = load_site_config("baseline-static", SITES_DIR)
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
        }
    )
    
    # Run crawl with enhanced preset
    enhanced_dir = tmp_path / "enhanced"
    enhanced_metrics, enhanced_markdown = _run_crawl_with_preset(
        config, "enhanced", enhanced_dir
    )
    
    # Run crawl with pure_crawl4ai preset
    pure_dir = tmp_path / "pure"
    pure_metrics, pure_markdown = _run_crawl_with_preset(
        config, "pure_crawl4ai", pure_dir
    )
    
    # Enhanced preset assertions (must meet quality thresholds)
    assert enhanced_metrics["total_pages"] >= 1, "Enhanced: Must crawl at least 1 page"
    assert enhanced_metrics["avg_word_count"] >= 50, (
        f"Enhanced: Insufficient content (avg_word_count={enhanced_metrics['avg_word_count']:.1f})"
    )
    assert enhanced_metrics["pages_with_headings"] >= 1, "Enhanced: Must have at least 1 page with headings"
    assert enhanced_metrics["manifest_exists"] is True, "Enhanced: Manifest must exist"
    assert enhanced_metrics["manifest_page_count"] == enhanced_metrics["total_pages"], (
        f"Enhanced: Manifest page count mismatch: "
        f"{enhanced_metrics['manifest_page_count']} != {enhanced_metrics['total_pages']}"
    )
    
    # Pure Crawl4AI preset assertions (minimal acceptability)
    assert pure_metrics["total_pages"] >= 1, "Pure: Must crawl at least 1 page"
    assert pure_metrics["avg_word_count"] >= 40, (
        f"Pure: Insufficient content (avg_word_count={pure_metrics['avg_word_count']:.1f})"
    )
    assert pure_metrics["pages_with_headings"] >= 1, "Pure: Must have at least 1 page with headings"
    assert pure_metrics["avg_link_count"] <= 100, (
        f"Pure: Too many links (avg_link_count={pure_metrics['avg_link_count']:.1f}), "
        "possible nav dump"
    )
    assert pure_metrics["manifest_exists"] is True, "Pure: Manifest must exist"
    assert pure_metrics["manifest_page_count"] == pure_metrics["total_pages"], (
        f"Pure: Manifest page count mismatch: "
        f"{pure_metrics['manifest_page_count']} != {pure_metrics['total_pages']}"
    )
    
    # Determinism check: run pure twice and compare hash
    pure_dir_2 = tmp_path / "pure2"
    pure_metrics_2, _ = _run_crawl_with_preset(config, "pure_crawl4ai", pure_dir_2)
    assert pure_metrics["content_hash_first_page"] == pure_metrics_2["content_hash_first_page"], (
        f"Pure preset not deterministic: "
        f"{pure_metrics['content_hash_first_page']} != {pure_metrics_2['content_hash_first_page']}"
    )
    
    # Determinism check: run enhanced twice and compare hash
    enhanced_dir_2 = tmp_path / "enhanced2"
    enhanced_metrics_2, _ = _run_crawl_with_preset(config, "enhanced", enhanced_dir_2)
    assert enhanced_metrics["content_hash_first_page"] == enhanced_metrics_2["content_hash_first_page"], (
        f"Enhanced preset not deterministic: "
        f"{enhanced_metrics['content_hash_first_page']} != {enhanced_metrics_2['content_hash_first_page']}"
    )
    
    # Optional: Write parity artefact if env var is set
    if os.getenv("WEB_SCRAPER_WRITE_PARITY_ARTEFACT") == "1":
        # Calculate deltas for numeric metrics
        delta: dict[str, object] = {}
        numeric_metrics = [
            "total_pages",
            "avg_word_count",
            "avg_char_count",
            "avg_heading_count",
            "avg_code_block_count",
            "avg_link_count",
            "pages_with_headings",
        ]
        for metric in numeric_metrics:
            if metric in pure_metrics and metric in enhanced_metrics:
                pure_val = pure_metrics[metric]
                enhanced_val = enhanced_metrics[metric]
                if isinstance(pure_val, (int, float)) and isinstance(enhanced_val, (int, float)):
                    delta[metric] = pure_val - enhanced_val
        
        parity_report = {
            "enhanced": enhanced_metrics,
            "pure_crawl4ai": pure_metrics,
            "delta": delta,
            "notes": {
                "enhanced_hash": enhanced_metrics["content_hash_first_page"],
                "pure_hash": pure_metrics["content_hash_first_page"],
            },
        }
        
        # Write report
        PARITY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_file = PARITY_REPORTS_DIR / "baseline-static.parity.json"
        report_file.write_text(
            json.dumps(parity_report, indent=2, sort_keys=True), encoding="utf-8"
        )
