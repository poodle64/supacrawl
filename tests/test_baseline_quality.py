"""Baseline quality harness for detecting crawl quality regressions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pytest

from web_scraper.models import Page, SiteConfig
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
from web_scraper.sites.loader import load_site_config

# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SITES_DIR = FIXTURES_DIR / "sites"
BASELINE_METRICS_FILE = FIXTURES_DIR / "baseline_metrics.json"

# Test site configs
BASELINE_SITES = [
    "baseline-simple",
    "baseline-multi",
    "baseline-static",
]


def _apply_fast_mode_config(config: SiteConfig) -> SiteConfig:
    """
    Apply fast mode settings to a SiteConfig for testing.
    
    This function modifies the config to reduce crawl time:
    - Reduces max_pages to minimum needed
    - Disables sitemap discovery
    - Disables link discovery workaround
    
    Args:
        config: Site configuration to modify.
        
    Returns:
        Modified SiteConfig instance.
    """
    # Reduce max_pages (cap at 5 for fast testing)
    max_pages = min(config.max_pages, 5)
    
    # Disable features that slow down tests
    return config.model_copy(
        update={
            "max_pages": max_pages,
            "sitemap": config.sitemap.model_copy(update={"enabled": False}),
        }
    )


def _calculate_page_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate page count metrics.
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with page count metrics.
    """
    unique_urls = len(set(page.url for page in pages))
    return {
        "total_pages": len(pages),
        "unique_urls": unique_urls,
    }


def _calculate_content_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate content size metrics.
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with content size metrics.
    """
    if not pages:
        return {
            "avg_word_count": 0.0,
            "avg_char_count": 0.0,
        }
    
    word_counts = [len(page.content_markdown.split()) for page in pages]
    char_counts = [len(page.content_markdown) for page in pages]
    
    return {
        "avg_word_count": sum(word_counts) / len(word_counts),
        "avg_char_count": sum(char_counts) / len(char_counts),
    }


def _calculate_structure_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate structure metrics (headings, code blocks).
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with structure metrics.
    """
    if not pages:
        return {
            "pages_with_headings": 0,
            "avg_heading_count": 0.0,
            "avg_code_block_count": 0.0,
        }
    
    heading_counts = []
    code_block_counts = []
    pages_with_headings = 0
    
    for page in pages:
        lines = page.content_markdown.splitlines()
        heading_count = sum(1 for line in lines if line.strip().startswith("#"))
        code_block_count = page.content_markdown.count("```") // 2  # Pairs of ```
        
        heading_counts.append(heading_count)
        code_block_counts.append(code_block_count)
        
        if heading_count > 0:
            pages_with_headings += 1
    
    return {
        "pages_with_headings": pages_with_headings,
        "avg_heading_count": sum(heading_counts) / len(heading_counts) if heading_counts else 0.0,
        "avg_code_block_count": sum(code_block_counts) / len(code_block_counts) if code_block_counts else 0.0,
    }


def _calculate_link_metrics(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate link metrics.
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with link metrics.
    """
    if not pages:
        return {
            "avg_link_count": 0.0,
        }
    
    link_counts = [page.content_markdown.count("](") for page in pages]
    
    return {
        "avg_link_count": sum(link_counts) / len(link_counts) if link_counts else 0.0,
    }


def _calculate_format_metrics(snapshot_path: Path) -> dict[str, Any]:
    """
    Calculate format metrics from snapshot filesystem.
    
    Args:
        snapshot_path: Path to snapshot root directory.
        
    Returns:
        Dictionary with format metrics.
    """
    manifest_path = snapshot_path / "manifest.json"
    manifest_exists = manifest_path.exists()
    
    manifest_page_count = 0
    if manifest_exists:
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_page_count = manifest_data.get("total_pages", 0)
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Count markdown files
    markdown_dir = snapshot_path / "markdown"
    markdown_files_written = 0
    if markdown_dir.exists():
        markdown_files_written = len(list(markdown_dir.rglob("*.md")))
    
    return {
        "markdown_files_written": markdown_files_written,
        "manifest_exists": manifest_exists,
        "manifest_page_count": manifest_page_count,
    }


def _calculate_determinism_metric(pages: list[Page]) -> dict[str, Any]:
    """
    Calculate determinism metric (content hash of first page).
    
    Args:
        pages: List of Page objects.
        
    Returns:
        Dictionary with determinism metric.
    """
    if not pages:
        return {
            "content_hash_first_page": "",
        }
    
    return {
        "content_hash_first_page": pages[0].content_hash,
    }


def calculate_all_metrics(pages: list[Page], snapshot_path: Path) -> dict[str, Any]:
    """
    Calculate all quality metrics for a crawl.
    
    Args:
        pages: List of Page objects from crawl.
        snapshot_path: Path to snapshot root directory.
        
    Returns:
        Dictionary with all quality metrics.
    """
    metrics = {}
    metrics.update(_calculate_page_metrics(pages))
    metrics.update(_calculate_content_metrics(pages))
    metrics.update(_calculate_structure_metrics(pages))
    metrics.update(_calculate_link_metrics(pages))
    metrics.update(_calculate_format_metrics(snapshot_path))
    metrics.update(_calculate_determinism_metric(pages))
    return metrics


@pytest.fixture(scope="session")
def baseline_metrics() -> dict[str, Any]:
    """
    Load baseline metrics from fixture file.
    
    Returns:
        Dictionary of baseline metrics by site_id.
    """
    if BASELINE_METRICS_FILE.exists():
        return json.loads(BASELINE_METRICS_FILE.read_text(encoding="utf-8"))
    return {}


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
    import time
    time.sleep(0.1)
    
    return base_url, httpd


@pytest.mark.parametrize("site_id", BASELINE_SITES)
def test_baseline_quality_capture(site_id: str, tmp_path: Path) -> None:
    """
    Capture baseline quality metrics from current implementation.
    
    Run this test once to establish baseline, then commit baseline_metrics.json.
    Set WEB_SCRAPER_CAPTURE_BASELINE=1 to enable.
    Set WEB_SCRAPER_FORCE_BASELINE=1 to overwrite existing baseline.
    
    Args:
        site_id: Site configuration ID to test.
        tmp_path: Temporary directory for test output.
    """
    # Only run if capture flag is set
    if not os.getenv("WEB_SCRAPER_CAPTURE_BASELINE"):
        pytest.skip("Set WEB_SCRAPER_CAPTURE_BASELINE=1 to capture baseline")
    
    # Hard fail if CI and capture flag is set (should not capture in CI)
    if os.getenv("CI") == "true":
        pytest.fail("Cannot capture baseline in CI. Run locally with WEB_SCRAPER_CAPTURE_BASELINE=1")
    
    # Check if baseline exists and force flag is not set
    if BASELINE_METRICS_FILE.exists() and not os.getenv("WEB_SCRAPER_FORCE_BASELINE"):
        existing = json.loads(BASELINE_METRICS_FILE.read_text(encoding="utf-8"))
        if site_id in existing:
            pytest.skip(
                f"Baseline already exists for {site_id}. "
                "Set WEB_SCRAPER_FORCE_BASELINE=1 to overwrite."
            )
    
    # Handle static site with local server
    if site_id == "baseline-static":
        base_url, server = _setup_static_server(tmp_path)
        # Update entrypoint to use local server
        config = load_site_config(site_id, SITES_DIR)
        config = config.model_copy(
            update={
                "entrypoints": [urljoin(base_url, "/index.html")],
                "include": [urljoin(base_url, "/**")],
            }
        )
    else:
        config = load_site_config(site_id, SITES_DIR)
    
    # Apply fast mode config
    config = _apply_fast_mode_config(config)
    
    # Crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Calculate metrics
    metrics = calculate_all_metrics(pages, snapshot_path)
    
    # Load existing baseline
    baseline = {}
    if BASELINE_METRICS_FILE.exists():
        baseline = json.loads(BASELINE_METRICS_FILE.read_text(encoding="utf-8"))
    
    # Update baseline for this site
    baseline[site_id] = metrics
    
    # Save baseline
    BASELINE_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_METRICS_FILE.write_text(json.dumps(baseline, indent=2, sort_keys=True), encoding="utf-8")
    
    # Basic sanity checks
    assert len(pages) > 0, f"{site_id}: No pages crawled"
    assert metrics["avg_word_count"] >= 10, f"{site_id}: Insufficient content (avg_word_count={metrics['avg_word_count']})"


@pytest.mark.parametrize("site_id", BASELINE_SITES)
def test_baseline_quality_assert(baseline_metrics: dict[str, Any], site_id: str, tmp_path: Path) -> None:
    """
    Assert current crawl quality matches baseline.
    
    This test runs on every CI run to detect regressions.
    Uses threshold-based assertions (80% of baseline) to avoid brittleness.
    
    Args:
        baseline_metrics: Baseline metrics dictionary (from fixture).
        site_id: Site configuration ID to test.
        tmp_path: Temporary directory for test output.
    """
    # Skip if baseline not captured
    if site_id not in baseline_metrics:
        pytest.skip(f"Baseline not captured for {site_id}. Run test_baseline_quality_capture first.")
    
    # Handle static site with local server
    if site_id == "baseline-static":
        base_url, server = _setup_static_server(tmp_path)
        # Update entrypoint to use local server
        config = load_site_config(site_id, SITES_DIR)
        config = config.model_copy(
            update={
                "entrypoints": [urljoin(base_url, "/index.html")],
                "include": [urljoin(base_url, "/**")],
            }
        )
    else:
        config = load_site_config(site_id, SITES_DIR)
    
    # Apply fast mode config
    config = _apply_fast_mode_config(config)
    
    # Crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Calculate metrics
    current_metrics = calculate_all_metrics(pages, snapshot_path)
    baseline = baseline_metrics[site_id]
    
    # Assertions with thresholds (80% of baseline)
    assert current_metrics["total_pages"] >= baseline["total_pages"] * 0.8, (
        f"{site_id}: Page count dropped significantly: "
        f"{current_metrics['total_pages']} < {baseline['total_pages'] * 0.8} "
        f"(baseline: {baseline['total_pages']})"
    )
    
    assert current_metrics["avg_word_count"] >= baseline["avg_word_count"] * 0.8, (
        f"{site_id}: Content size dropped significantly: "
        f"{current_metrics['avg_word_count']:.1f} < {baseline['avg_word_count'] * 0.8:.1f} "
        f"(baseline: {baseline['avg_word_count']:.1f})"
    )
    
    assert current_metrics["pages_with_headings"] >= baseline["pages_with_headings"] * 0.8, (
        f"{site_id}: Heading structure degraded: "
        f"{current_metrics['pages_with_headings']} < {baseline['pages_with_headings'] * 0.8} "
        f"(baseline: {baseline['pages_with_headings']})"
    )
    
    # Exact matches for manifest
    assert current_metrics["manifest_exists"] == baseline["manifest_exists"], (
        f"{site_id}: Manifest existence changed: "
        f"{current_metrics['manifest_exists']} != {baseline['manifest_exists']}"
    )
    
    assert current_metrics["manifest_page_count"] == current_metrics["total_pages"], (
        f"{site_id}: Manifest page count mismatch: "
        f"{current_metrics['manifest_page_count']} != {current_metrics['total_pages']}"
    )


@pytest.mark.parametrize("site_id", ["baseline-static"])
def test_baseline_determinism(site_id: str, tmp_path: Path) -> None:
    """
    Test determinism by running crawl twice and comparing content hash.
    
    Only runs for baseline-static (local file, no network variability).
    
    Args:
        site_id: Site configuration ID to test (must be baseline-static).
        tmp_path: Temporary directory for test output.
    """
    # Set up local server
    base_url, server = _setup_static_server(tmp_path)
    
    # Load and modify config
    config = load_site_config(site_id, SITES_DIR)
    config = config.model_copy(
        update={
            "entrypoints": [urljoin(base_url, "/index.html")],
            "include": [urljoin(base_url, "/**")],
        }
    )
    config = _apply_fast_mode_config(config)
    
    # Run crawl twice
    scraper = Crawl4AIScraper()
    
    # First crawl
    corpora_dir_1 = tmp_path / "run1"
    pages_1, snapshot_path_1 = scraper.crawl(config, corpora_dir=corpora_dir_1)
    metrics_1 = calculate_all_metrics(pages_1, snapshot_path_1)
    
    # Second crawl
    corpora_dir_2 = tmp_path / "run2"
    pages_2, snapshot_path_2 = scraper.crawl(config, corpora_dir=corpora_dir_2)
    metrics_2 = calculate_all_metrics(pages_2, snapshot_path_2)
    
    # Assert content hash is identical
    assert metrics_1["content_hash_first_page"] == metrics_2["content_hash_first_page"], (
        f"{site_id}: Content hash not deterministic: "
        f"{metrics_1['content_hash_first_page']} != {metrics_2['content_hash_first_page']}"
    )
    
    # Assert page count is identical
    assert metrics_1["total_pages"] == metrics_2["total_pages"], (
        f"{site_id}: Page count not deterministic: "
        f"{metrics_1['total_pages']} != {metrics_2['total_pages']}"
    )
