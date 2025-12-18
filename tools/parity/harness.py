"""Main parity harness for running comparisons."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from web_scraper.models import SiteConfig
from tools.parity.cache import get_cache_path, read_cache, write_cache
from tools.parity.metrics import (
    calculate_artefact_metrics,
    calculate_similarity_metrics,
)
from tools.parity.providers import (
    APIFirecrawlProvider,
    get_firecrawl_provider,
)
from tools.parity.urls import PARITY_TEST_URLS
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper

LOGGER = logging.getLogger(__name__)


async def _scrape_baseline_static(url: str, output_dir: Path) -> dict[str, Any]:
    """
    Scrape URL with baseline-static configuration (pure_crawl4ai, fixes disabled).

    Args:
        url: URL to scrape.
        output_dir: Directory for output.

    Returns:
        Dictionary with markdown content and metadata.
    """
    from web_scraper.exceptions import generate_correlation_id
    from web_scraper.corpus.writer import IncrementalSnapshotWriter
    from web_scraper.scrapers.crawl4ai import _crawl_settings_summary

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
    correlation_id = generate_correlation_id()
    snapshot_writer = IncrementalSnapshotWriter(
        config,
        output_dir,
        resume_snapshot=None,
    )
    snapshot_writer.crawl_settings = _crawl_settings_summary()
    
    try:
        pages = await scraper._crawl_async(config, correlation_id, snapshot_writer, None, None)
        await snapshot_writer.complete()
        
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
    except Exception as exc:
        await snapshot_writer.abort(str(exc))
        return {
            "markdown": "",
            "url": url,
            "success": False,
            "error": str(exc),
        }


async def _scrape_enhanced(url: str, output_dir: Path) -> dict[str, Any]:
    """
    Scrape URL with enhanced configuration (enhanced preset, fixes enabled).

    Args:
        url: URL to scrape.
        output_dir: Directory for output.

    Returns:
        Dictionary with markdown content and metadata.
    """
    from web_scraper.exceptions import generate_correlation_id
    from web_scraper.corpus.writer import IncrementalSnapshotWriter
    from web_scraper.scrapers.crawl4ai import _crawl_settings_summary

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
    correlation_id = generate_correlation_id()
    snapshot_writer = IncrementalSnapshotWriter(
        config,
        output_dir,
        resume_snapshot=None,
    )
    snapshot_writer.crawl_settings = _crawl_settings_summary()
    
    try:
        pages = await scraper._crawl_async(config, correlation_id, snapshot_writer, None, None)
        await snapshot_writer.complete()
        
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
    except Exception as exc:
        await snapshot_writer.abort(str(exc))
        return {
            "markdown": "",
            "url": url,
            "success": False,
            "error": str(exc),
        }


async def run_parity_comparison(
    output_dir: Path,
    urls: list[str] | None = None,
    max_urls: int | None = None,
    no_cache: bool = False,
    cache_only: bool = False,
) -> dict[str, Any]:
    """
    Run full parity comparison across test URLs.

    Args:
        output_dir: Directory for output files.
        urls: Optional list of URLs to test (overrides default).
        max_urls: Maximum number of URLs to process.
        no_cache: Force re-fetch (ignore cache).
        cache_only: Only use cache, fail if missing.

    Returns:
        Dictionary with complete comparison results.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "cache" / "firecrawl"

    # Determine URLs to test
    test_urls = urls if urls else PARITY_TEST_URLS
    if max_urls:
        test_urls = test_urls[:max_urls]

    # Sort URLs for deterministic ordering
    test_urls = sorted(test_urls)

    # Determine Firecrawl provider
    provider = get_firecrawl_provider()
    provider_name = "none"
    if isinstance(provider, APIFirecrawlProvider):
        provider_name = "api"

    firecrawl_available = provider_name != "none"

    results: list[dict[str, Any]] = []

    LOGGER.info(f"Starting parity comparison for {len(test_urls)} URLs")
    LOGGER.info(f"Firecrawl provider: {provider_name}")

    for url in test_urls:
        LOGGER.info(f"Processing {url}")

        # Scrape with Firecrawl
        firecrawl_markdown: str | None = None
        if firecrawl_available:
            # Get the provider instance
            provider = get_firecrawl_provider()
            if provider:
                # Check cache first
                cached_content = None
                if cache_dir and not no_cache:
                    cache_path = get_cache_path(cache_dir, url, provider_name)
                    cached_content = read_cache(cache_path)
                    if cached_content:
                        LOGGER.info(f"Using cached Firecrawl content for {url}")
                        firecrawl_markdown = cached_content

                if not firecrawl_markdown:
                    if cache_only:
                        LOGGER.error(f"Cache-only mode: no cache found for {url}")
                        firecrawl_markdown = None
                    else:
                        # Scrape with provider (API only)
                        if isinstance(provider, APIFirecrawlProvider):
                            firecrawl_markdown = await provider.scrape_markdown(url)
                        else:
                            LOGGER.warning(f"No Firecrawl provider available for {url}")
                            firecrawl_markdown = None

                    # Write to cache if successful
                    if firecrawl_markdown and cache_dir:
                        cache_path = get_cache_path(cache_dir, url, provider_name)
                        write_cache(cache_path, firecrawl_markdown)
        else:
            LOGGER.warning(f"Firecrawl not available for {url}, skipping Firecrawl comparison")

        # Scrape with baseline-static
        baseline_dir = output_dir / "baseline" / _url_to_slug(url)
        baseline_result = await _scrape_baseline_static(url, baseline_dir)
        baseline_markdown = baseline_result["markdown"]

        # Scrape with enhanced
        enhanced_dir = output_dir / "enhanced" / _url_to_slug(url)
        enhanced_result = await _scrape_enhanced(url, enhanced_dir)
        enhanced_markdown = enhanced_result["markdown"]

        # Calculate metrics for each artefact
        firecrawl_markdown_str = firecrawl_markdown or ""
        firecrawl_metrics = (
            calculate_artefact_metrics(firecrawl_markdown_str) if firecrawl_markdown_str else {}
        )
        baseline_metrics = (
            calculate_artefact_metrics(baseline_markdown) if baseline_markdown else {}
        )
        enhanced_metrics = (
            calculate_artefact_metrics(enhanced_markdown) if enhanced_markdown else {}
        )

        # Calculate similarity metrics
        similarity_metrics = {}
        if firecrawl_markdown_str and baseline_markdown and enhanced_markdown:
            similarity_metrics = calculate_similarity_metrics(
                firecrawl_markdown_str, baseline_markdown, enhanced_markdown
            )

        # Store results
        url_result = {
            "url": url,
            "firecrawl": {
                "success": bool(firecrawl_markdown_str),
                "provider": provider_name,
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

    # Calculate fixes subsystem value metrics
    fixes_metrics = _calculate_fixes_metrics(results)

    # Generate decision gate
    decision = _generate_decision_gate(results, aggregate, fixes_metrics)

    return {
        "timestamp": datetime.now().isoformat(),
        "urls_tested": len(test_urls),
        "firecrawl_provider": provider_name,
        "firecrawl_available": firecrawl_available,
        "results": results,
        "aggregate": aggregate,
        "fixes_metrics": fixes_metrics,
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


def _calculate_fixes_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate metrics specific to fixes subsystem value.

    Args:
        results: Per-URL comparison results.

    Returns:
        Dictionary with fixes-specific metrics.
    """
    # Count URLs where enhanced improves "links missing anchor text" vs baseline
    improved_missing_links: list[str] = []
    total_missing_links_baseline = 0
    total_missing_links_enhanced = 0

    for result in results:
        baseline_metrics = result["baseline_static"]["metrics"]
        enhanced_metrics = result["enhanced"]["metrics"]

        baseline_missing = baseline_metrics.get("links_missing_text", 0)
        enhanced_missing = enhanced_metrics.get("links_missing_text", 0)

        total_missing_links_baseline += baseline_missing
        total_missing_links_enhanced += enhanced_missing

        if enhanced_missing < baseline_missing:
            improved_missing_links.append(result["url"])

    # Calculate similarity improvements
    similarity_improvements = []
    for result in results:
        if result["similarity"]:
            sim = result["similarity"]
            improvement = sim["firecrawl_vs_enhanced"] - sim["firecrawl_vs_baseline"]
            similarity_improvements.append(improvement)

    avg_similarity_improvement = (
        sum(similarity_improvements) / len(similarity_improvements)
        if similarity_improvements
        else 0.0
    )

    return {
        "urls_with_improved_missing_links": len(improved_missing_links),
        "urls_with_improved_missing_links_list": improved_missing_links,
        "total_missing_links_baseline": total_missing_links_baseline,
        "total_missing_links_enhanced": total_missing_links_enhanced,
        "missing_links_delta": total_missing_links_enhanced - total_missing_links_baseline,
        "avg_similarity_improvement": avg_similarity_improvement,
    }


def _generate_decision_gate(
    results: list[dict[str, Any]],
    aggregate: dict[str, Any],
    fixes_metrics: dict[str, Any],
) -> dict[str, Any]:
    """
    Generate decision gate recommendation based on metrics.

    Args:
        results: Per-URL comparison results.
        aggregate: Aggregate metrics.
        fixes_metrics: Fixes-specific metrics.

    Returns:
        Dictionary with decision gate analysis.
    """
    # Thresholds for "material difference"
    SIMILARITY_THRESHOLD = 0.05  # 5% improvement
    SUCCESS_RATE_THRESHOLD = 0.10  # 10% improvement
    MISSING_LINKS_IMPROVEMENT_THRESHOLD = 0.10  # 10% of URLs show improvement

    firecrawl_vs_baseline = aggregate["avg_similarity"]["firecrawl_vs_baseline"]
    firecrawl_vs_enhanced = aggregate["avg_similarity"]["firecrawl_vs_enhanced"]
    baseline_vs_enhanced = aggregate["avg_similarity"]["baseline_vs_enhanced"]

    # Does enhanced outperform baseline?
    enhanced_outperforms_baseline = baseline_vs_enhanced < 0.95  # Enhanced is different
    enhanced_closer_to_firecrawl = (
        firecrawl_vs_enhanced > firecrawl_vs_baseline + SIMILARITY_THRESHOLD
    )

    # Success rate comparison
    baseline_success = aggregate["success_rates"]["baseline_static"]
    enhanced_success = aggregate["success_rates"]["enhanced"]
    success_rate_improvement = enhanced_success - baseline_success

    # Missing links improvement
    missing_links_improvement_rate = (
        fixes_metrics["urls_with_improved_missing_links"] / len(results)
        if results
        else 0.0
    )
    missing_links_delta = fixes_metrics["missing_links_delta"]

    # Decision logic
    if (
        enhanced_closer_to_firecrawl
        and success_rate_improvement >= SUCCESS_RATE_THRESHOLD
    ):
        recommendation = "KEEP_FIXES"
        reason = (
            f"Enhanced output is {((firecrawl_vs_enhanced - firecrawl_vs_baseline) * 100):.1f}% "
            f"closer to Firecrawl and has {success_rate_improvement * 100:.1f}% better success rate"
        )
    elif enhanced_closer_to_firecrawl:
        recommendation = "KEEP_FIXES"
        reason = (
            f"Enhanced output is {((firecrawl_vs_enhanced - firecrawl_vs_baseline) * 100):.1f}% "
            "closer to Firecrawl (success rate similar)"
        )
    elif (
        missing_links_improvement_rate >= MISSING_LINKS_IMPROVEMENT_THRESHOLD
        and missing_links_delta < 0
    ):
        recommendation = "KEEP_FIXES"
        reason = (
            f"Enhanced output improves missing anchor text links on "
            f"{fixes_metrics['urls_with_improved_missing_links']} URLs "
            f"({missing_links_improvement_rate * 100:.1f}%)"
        )
    elif enhanced_outperforms_baseline and baseline_vs_enhanced < 0.90:
        recommendation = "KEEP_FIXES"
        reason = "Enhanced output is materially different from baseline (may indicate fixes are working)"
    else:
        recommendation = "REMOVE_FIXES"
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
            "missing_links_improvement_rate": missing_links_improvement_rate,
            "missing_links_delta": missing_links_delta,
        },
    }
