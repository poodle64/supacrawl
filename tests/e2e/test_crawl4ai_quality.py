"""Quality comparison tests: Crawl4AI implementation vs Firecrawl benchmarks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from web_scraper.models import SiteConfig
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

# Project root for saving results
PROJECT_ROOT = Path(__file__).parent.parent

# Test URLs from meta.yaml - diverse set for comprehensive testing
TEST_URLS = [
    "https://developers.facebook.com/docs/graph-api/overview",
    "https://developers.facebook.com/docs/graph-api/guides/error-handling",
    "https://developers.facebook.com/docs/graph-api/results",
    "https://developers.facebook.com/docs/graph-api/batch-requests",
    "https://developers.facebook.com/docs/graph-api/guides/field-expansion",
    "https://developers.facebook.com/docs/graph-api/guides/secure-requests",
    "https://developers.facebook.com/docs/graph-api/get-started",
    "https://developers.facebook.com/docs/graph-api/reference/application",
    "https://developers.facebook.com/docs/graph-api/reference/page",
    "https://developers.facebook.com/docs/graph-api/reference/user",
    "https://developers.facebook.com/docs/graph-api/reference/post",
    "https://developers.facebook.com/docs/graph-api/reference/comment",
    "https://developers.facebook.com/docs/graph-api/reference/debug_token",
    "https://developers.facebook.com/docs/graph-api/webhooks",
    "https://developers.facebook.com/docs/graph-api/webhooks/reference",
    "https://developers.facebook.com/docs/app-management/",
    "https://developers.facebook.com/docs/marketing-api/overview",
    "https://developers.facebook.com/docs/marketing-api/get-started/authorization",
    "https://developers.facebook.com/docs/marketing-api/guides/lead-ads/create/",
    "https://developers.facebook.com/docs/marketing-api/guides/lead-ads/retrieving/",
]


def _test_config(url: str) -> SiteConfig:
    """Create a test site config for a single URL."""
    return SiteConfig(
        id="test-quality",
        name="Quality Test",
        entrypoints=[url],
        include=[f"{url}**"],
        exclude=[],
        max_pages=1,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
    )


def _calculate_quality_metrics(markdown: str) -> dict[str, Any]:
    """
    Calculate content quality metrics for comparison.

    Returns:
        Dictionary with quality metrics.
    """
    if not markdown:
        return {
            "word_count": 0,
            "heading_count": 0,
            "code_block_count": 0,
            "link_count": 0,
            "link_density": 0.0,
            "boilerplate_score": 0.0,
            "content_density": 0.0,
            "has_main_content": False,
        }

    lines = markdown.splitlines()
    words = markdown.split()
    word_count = len(words)

    # Count headings
    heading_count = sum(1 for line in lines if line.strip().startswith("#"))

    # Count code blocks
    code_block_count = markdown.count("```")

    # Count links
    link_count = markdown.count("](")

    # Calculate link density (high = navigation-heavy)
    link_density = link_count / word_count if word_count > 0 else 0.0

    # Boilerplate indicators
    boilerplate_keywords = [
        "cookie",
        "privacy policy",
        "terms of service",
        "navigation",
        "menu",
        "footer",
        "sidebar",
        "advertisement",
        "subscribe",
        "newsletter",
        "social media",
        "on this page",  # Common navigation element
        "docs",  # Navigation links
        "tools",  # Navigation links
        "support",  # Navigation links
    ]
    boilerplate_matches = sum(
        1 for keyword in boilerplate_keywords if keyword.lower() in markdown.lower()
    )
    boilerplate_score = min(boilerplate_matches / 10.0, 1.0)

    # Content density (non-empty lines / total lines)
    non_empty_lines = sum(1 for line in lines if line.strip())
    content_density = non_empty_lines / len(lines) if lines else 0.0

    # Check for main content indicators
    main_content_indicators = [
        "##",  # H2 headings (usually main content)
        "```",  # Code blocks
        "graph.facebook.com",  # API examples
        "curl",  # Code examples
        "api",  # API references
    ]
    has_main_content = any(indicator in markdown for indicator in main_content_indicators)

    return {
        "word_count": word_count,
        "heading_count": heading_count,
        "code_block_count": code_block_count,
        "link_count": link_count,
        "link_density": link_density,
        "boilerplate_score": boilerplate_score,
        "content_density": content_density,
        "has_main_content": has_main_content,
    }


def test_crawl4ai_quality_on_test_urls() -> None:
    """
    Test Crawl4AI implementation quality on test URLs.

    This test scrapes URLs with our implementation and calculates quality metrics.
    Results can be compared against Firecrawl benchmarks.
    """
    import os
    import tempfile

    # Skip if running in CI without proper setup
    if os.getenv("CI") and not os.getenv("CRAWL4AI_TEST_ENABLED"):
        pytest.skip("Skipping integration test in CI without CRAWL4AI_TEST_ENABLED")

    results: list[dict[str, Any]] = []
    scraper = Crawl4AIScraper()

    # Test all URLs
    for i, url in enumerate(TEST_URLS, 1):
        LOGGER.info(f"[{i}/{len(TEST_URLS)}] Testing: {url}")

        try:
            config = _test_config(url)

            with tempfile.TemporaryDirectory() as tmpdir:
                pages, snapshot_path = scraper.crawl(config, corpora_dir=Path(tmpdir))

                if pages:
                    content = pages[0].content_markdown
                    metrics = _calculate_quality_metrics(content)
                    success = True
                    error = None
                else:
                    content = ""
                    metrics = _calculate_quality_metrics("")
                    success = False
                    error = "No pages returned"
        except Exception as e:
            LOGGER.error(f"Crawl4AI failed for {url}: {e}")
            content = ""
            metrics = _calculate_quality_metrics("")
            success = False
            error = str(e)

        results.append(
            {
                "url": url,
                "success": success,
                "metrics": metrics,
                "content_length": len(content),
                "content_preview": content[:500] if content else "",
                "error": error,
            }
        )

        if success:
            LOGGER.info(
                f"  ✓ {metrics['word_count']} words, "
                f"{metrics['heading_count']} headings, "
                f"boilerplate={metrics['boilerplate_score']:.2f}"
            )
        else:
            LOGGER.warning(f"  ✗ Failed: {error}")

    # Save results
    results_file = Path(__file__).parent.parent / "fixtures" / "test_crawl4ai_quality_results.json"
    with results_file.open("w") as f:
        json.dump(results, f, indent=2)

    # Calculate statistics
    success_count = sum(1 for r in results if r["success"])
    if success_count > 0:
        successful_results = [r for r in results if r["success"]]
        avg_word_count = sum(r["metrics"]["word_count"] for r in successful_results) / success_count
        avg_boilerplate = sum(r["metrics"]["boilerplate_score"] for r in successful_results) / success_count
        avg_content_density = sum(r["metrics"]["content_density"] for r in successful_results) / success_count

        LOGGER.info("")
        LOGGER.info("=" * 60)
        LOGGER.info("Crawl4AI Quality Statistics:")
        LOGGER.info(f"  Success rate: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
        LOGGER.info(f"  Average word count: {avg_word_count:.0f}")
        LOGGER.info(f"  Average boilerplate score: {avg_boilerplate:.3f} (lower is better)")
        LOGGER.info(f"  Average content density: {avg_content_density:.3f} (higher is better)")
        LOGGER.info(f"  Results saved to: {results_file}")
        LOGGER.info("=" * 60)

    assert success_count > 0, "At least some scrapes should succeed"


if __name__ == "__main__":
    import os

    # Set test flag if not in CI
    if not os.getenv("CI"):
        os.environ["CRAWL4AI_TEST_ENABLED"] = "true"
    test_crawl4ai_quality_on_test_urls()
