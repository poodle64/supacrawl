"""Main parity harness for running comparisons."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from web_scraper.models import SiteConfig
from web_scraper.parity.firecrawl import scrape_with_firecrawl
from web_scraper.parity.metrics import (
    calculate_artefact_metrics,
    calculate_similarity_metrics,
)
from web_scraper.parity.urls import PARITY_TEST_URLS
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper

LOGGER = logging.getLogger(__name__)


def _scrape_baseline_static(url: str, output_dir: Path) -> dict[str, Any]:
    """
    Scrape URL with baseline-static configuration (pure_crawl4ai, fixes disabled).

    Args:
        url: URL to scrape.
        output_dir: Directory for output.

    Returns:
        Dictionary with markdown content and metadata.
    """
    config = SiteConfig(
        id="parity-baseline",
        name="Parity Baseline",
        entrypoints=[url],
        include=[f"{url}**"],
        exclude=[],
        max_pages=1,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
        markdown_quality_preset="pure_crawl4ai",
    )
    config.markdown_fixes.enabled = False

    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=output_dir)

    if pages:
        return {
            "markdown": pages[0].content_markdown,
            "url": url,
            "success": True,
        }
    return {
        "markdown": "",
        "url": url,
        "success": False,
        "error": "No pages returned",
    }


def _scrape_enhanced(url: str, output_dir: Path) -> dict[str, Any]:
    """
    Scrape URL with enhanced configuration (enhanced preset, fixes enabled).

    Args:
        url: URL to scrape.
        output_dir: Directory for output.

    Returns:
        Dictionary with markdown content and metadata.
    """
    config = SiteConfig(
        id="parity-enhanced",
        name="Parity Enhanced",
        entrypoints=[url],
        include=[f"{url}**"],
        exclude=[],
        max_pages=1,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
        markdown_quality_preset="enhanced",
    )
    config.markdown_fixes.enabled = True

    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=output_dir)

    if pages:
        return {
            "markdown": pages[0].content_markdown,
            "url": url,
            "success": True,
        }
    return {
        "markdown": "",
        "url": url,
        "success": False,
        "error": "No pages returned",
    }


async def run_parity_comparison(output_dir: Path) -> dict[str, Any]:
    """
    Run full parity comparison across all test URLs.

    Args:
        output_dir: Directory for output files.

    Returns:
        Dictionary with complete comparison results.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    LOGGER.info(f"Starting parity comparison for {len(PARITY_TEST_URLS)} URLs")

    for url in PARITY_TEST_URLS:
        LOGGER.info(f"Processing {url}")

        # Scrape with Firecrawl
        firecrawl_result = await scrape_with_firecrawl(url)
        firecrawl_markdown = firecrawl_result["markdown"] if firecrawl_result else ""

        # Scrape with baseline-static
        baseline_dir = output_dir / "baseline" / _url_to_slug(url)
        baseline_result = _scrape_baseline_static(url, baseline_dir)
        baseline_markdown = baseline_result["markdown"]

        # Scrape with enhanced
        enhanced_dir = output_dir / "enhanced" / _url_to_slug(url)
        enhanced_result = _scrape_enhanced(url, enhanced_dir)
        enhanced_markdown = enhanced_result["markdown"]

        # Calculate metrics for each artefact
        firecrawl_metrics = (
            calculate_artefact_metrics(firecrawl_markdown) if firecrawl_markdown else {}
        )
        baseline_metrics = (
            calculate_artefact_metrics(baseline_markdown) if baseline_markdown else {}
        )
        enhanced_metrics = (
            calculate_artefact_metrics(enhanced_markdown) if enhanced_markdown else {}
        )

        # Calculate similarity metrics
        similarity_metrics = {}
        if firecrawl_markdown and baseline_markdown and enhanced_markdown:
            similarity_metrics = calculate_similarity_metrics(
                firecrawl_markdown, baseline_markdown, enhanced_markdown
            )

        # Store results
        url_result = {
            "url": url,
            "firecrawl": {
                "success": firecrawl_result["success"] if firecrawl_result else False,
                "metrics": firecrawl_metrics,
            },
            "baseline_static": {
                "success": baseline_result["success"],
                "metrics": baseline_metrics,
            },
            "enhanced": {
                "success": enhanced_result["success"],
                "metrics": enhanced_metrics,
            },
            "similarity": similarity_metrics,
        }

        results.append(url_result)

        # Small delay to avoid rate limiting
        await asyncio.sleep(1)

    # Calculate aggregate metrics
    aggregate = _calculate_aggregate_metrics(results)

    # Generate decision gate
    decision = _generate_decision_gate(results, aggregate)

    return {
        "timestamp": datetime.now().isoformat(),
        "urls_tested": len(PARITY_TEST_URLS),
        "results": results,
        "aggregate": aggregate,
        "decision": decision,
    }


def _url_to_slug(url: str) -> str:
    """Convert URL to filesystem-safe slug."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "-")
    return path or "index"


def _calculate_aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate aggregate metrics across all URLs."""
    successful_firecrawl = sum(1 for r in results if r["firecrawl"]["success"])
    successful_baseline = sum(1 for r in results if r["baseline_static"]["success"])
    successful_enhanced = sum(1 for r in results if r["enhanced"]["success"])

    # Aggregate similarity scores
    similarities = [r["similarity"] for r in results if r["similarity"]]
    avg_firecrawl_vs_baseline = (
        sum(s["firecrawl_vs_baseline"] for s in similarities) / len(similarities)
        if similarities
        else 0.0
    )
    avg_firecrawl_vs_enhanced = (
        sum(s["firecrawl_vs_enhanced"] for s in similarities) / len(similarities)
        if similarities
        else 0.0
    )
    avg_baseline_vs_enhanced = (
        sum(s["baseline_vs_enhanced"] for s in similarities) / len(similarities)
        if similarities
        else 0.0
    )

    return {
        "success_rates": {
            "firecrawl": successful_firecrawl / len(results) if results else 0.0,
            "baseline_static": successful_baseline / len(results) if results else 0.0,
            "enhanced": successful_enhanced / len(results) if results else 0.0,
        },
        "avg_similarity": {
            "firecrawl_vs_baseline": avg_firecrawl_vs_baseline,
            "firecrawl_vs_enhanced": avg_firecrawl_vs_enhanced,
            "baseline_vs_enhanced": avg_baseline_vs_enhanced,
        },
    }


def _generate_decision_gate(
    results: list[dict[str, Any]], aggregate: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate decision gate recommendation based on metrics.

    Args:
        results: Per-URL comparison results.
        aggregate: Aggregate metrics.

    Returns:
        Dictionary with decision gate analysis.
    """
    # Thresholds for "material difference"
    SIMILARITY_THRESHOLD = 0.05  # 5% improvement
    SUCCESS_RATE_THRESHOLD = 0.10  # 10% improvement

    firecrawl_vs_baseline = aggregate["avg_similarity"]["firecrawl_vs_baseline"]
    firecrawl_vs_enhanced = aggregate["avg_similarity"]["firecrawl_vs_enhanced"]
    baseline_vs_enhanced = aggregate["avg_similarity"]["baseline_vs_enhanced"]

    # Does enhanced outperform baseline?
    enhanced_outperforms_baseline = baseline_vs_enhanced < 0.95  # Enhanced is different
    enhanced_closer_to_firecrawl = firecrawl_vs_enhanced > firecrawl_vs_baseline + SIMILARITY_THRESHOLD

    # Success rate comparison
    baseline_success = aggregate["success_rates"]["baseline_static"]
    enhanced_success = aggregate["success_rates"]["enhanced"]
    success_rate_improvement = enhanced_success - baseline_success

    # Decision logic
    if enhanced_closer_to_firecrawl and success_rate_improvement >= SUCCESS_RATE_THRESHOLD:
        recommendation = "KEEP"
        reason = (
            f"Enhanced output is {((firecrawl_vs_enhanced - firecrawl_vs_baseline) * 100):.1f}% "
            f"closer to Firecrawl and has {success_rate_improvement * 100:.1f}% better success rate"
        )
    elif enhanced_closer_to_firecrawl:
        recommendation = "KEEP"
        reason = (
            f"Enhanced output is {((firecrawl_vs_enhanced - firecrawl_vs_baseline) * 100):.1f}% "
            "closer to Firecrawl (success rate similar)"
        )
    elif enhanced_outperforms_baseline and baseline_vs_enhanced < 0.90:
        recommendation = "KEEP"
        reason = "Enhanced output is materially different from baseline (may indicate fixes are working)"
    else:
        recommendation = "REMOVE"
        reason = (
            "Enhanced output does not materially outperform baseline-static or close gap to Firecrawl. "
            f"Similarity difference: {((firecrawl_vs_enhanced - firecrawl_vs_baseline) * 100):.1f}%"
        )

    return {
        "recommendation": recommendation,
        "reason": reason,
        "metrics": {
            "firecrawl_vs_baseline_similarity": firecrawl_vs_baseline,
            "firecrawl_vs_enhanced_similarity": firecrawl_vs_enhanced,
            "baseline_vs_enhanced_similarity": baseline_vs_enhanced,
            "similarity_improvement": firecrawl_vs_enhanced - firecrawl_vs_baseline,
            "baseline_success_rate": baseline_success,
            "enhanced_success_rate": enhanced_success,
            "success_rate_improvement": success_rate_improvement,
        },
    }

