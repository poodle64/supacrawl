#!/usr/bin/env python3
"""Benchmark LLM-based content identification.

Measures:
- Token counts (input/output)
- Cost estimates
- Accuracy (does selector find content?)
- Time per request
- Cache hit rate

Usage:
    python scripts/benchmark_llm_content.py

Set OPENAI_API_KEY or ANTHROPIC_API_KEY to use hosted APIs (recommended).
Falls back to local Ollama if no API key is set.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from web_scraper.llm_content import DOMSkeleton, LLMContentIdentifier
from web_scraper.converter import MarkdownConverter


# Test URLs covering different site types
TEST_URLS = [
    # Documentation sites
    ("https://docs.python.org/3/tutorial/classes.html", "Python Docs"),
    ("https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Functions", "MDN"),
    # News/blogs
    ("https://news.ycombinator.com/", "Hacker News"),
    # E-commerce
    ("https://www.example.com/", "Example.com"),
]

# Token cost estimates (per 1M tokens) - GPT-4o-mini pricing
COST_PER_MILLION_INPUT = 0.15  # $0.15 per 1M input tokens
COST_PER_MILLION_OUTPUT = 0.60  # $0.60 per 1M output tokens


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token average)."""
    return len(text) // 4


def format_cost(dollars: float) -> str:
    """Format cost in readable form."""
    if dollars < 0.0001:
        return f"${dollars:.6f}"
    elif dollars < 0.01:
        return f"${dollars:.4f}"
    else:
        return f"${dollars:.2f}"


async def fetch_page(url: str) -> str | None:
    """Fetch a page's HTML content."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                follow_redirects=True,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            )
            return response.text
    except Exception as e:
        print(f"  Failed to fetch {url}: {e}")
        return None


async def benchmark_url(
    url: str,
    name: str,
    identifier: LLMContentIdentifier,
    converter: MarkdownConverter
) -> dict | None:
    """Benchmark a single URL."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")

    # Fetch page
    html = await fetch_page(url)
    if not html:
        return None

    print(f"  HTML size: {len(html):,} chars (~{estimate_tokens(html):,} tokens)")

    # Extract skeleton
    skeleton = DOMSkeleton(html).extract(max_depth=3)
    skeleton_tokens = estimate_tokens(skeleton)
    print(f"  Skeleton size: {len(skeleton):,} chars (~{skeleton_tokens:,} tokens)")
    print(f"  Compression ratio: {len(html) / len(skeleton):.1f}x")

    # Show skeleton preview
    print(f"\n  Skeleton preview:")
    for line in skeleton.split("\n")[:15]:
        print(f"    {line}")
    if skeleton.count("\n") > 15:
        print(f"    ... ({skeleton.count(chr(10)) - 15} more lines)")

    # Time the LLM identification
    start = time.perf_counter()
    selector = identifier.identify_selector(html, url, use_cache=False)
    elapsed = time.perf_counter() - start

    print(f"\n  LLM Response:")
    print(f"    Selector: {selector}")
    print(f"    Time: {elapsed:.2f}s")

    # Estimate costs
    input_cost = (skeleton_tokens / 1_000_000) * COST_PER_MILLION_INPUT
    output_cost = (20 / 1_000_000) * COST_PER_MILLION_OUTPUT  # ~20 output tokens
    total_cost = input_cost + output_cost

    print(f"\n  Cost estimate:")
    print(f"    Input: {format_cost(input_cost)} ({skeleton_tokens} tokens)")
    print(f"    Output: {format_cost(output_cost)} (~20 tokens)")
    print(f"    Total: {format_cost(total_cost)}")

    # Validate selector
    if selector:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        element = soup.select_one(selector)
        if element:
            content_len = len(element.get_text(strip=True))
            print(f"\n  Validation:")
            print(f"    ✓ Selector matched element")
            print(f"    Content length: {content_len:,} chars")

            # Compare with trafilatura
            traf_md = converter.convert(html, url)
            print(f"    Trafilatura output: {len(traf_md):,} chars")
        else:
            print(f"\n  Validation:")
            print(f"    ✗ Selector did not match any element")

    return {
        "url": url,
        "name": name,
        "html_size": len(html),
        "skeleton_size": len(skeleton),
        "skeleton_tokens": skeleton_tokens,
        "selector": selector,
        "time_seconds": elapsed,
        "cost_usd": total_cost,
    }


async def main():
    """Run benchmark suite."""
    print("=" * 60)
    print("LLM Content Identification Benchmark")
    print("=" * 60)

    # Create identifier (auto-detects provider)
    identifier = LLMContentIdentifier()
    converter = MarkdownConverter()

    # Show which provider is being used
    provider = identifier._provider
    print(f"\nUsing provider: {provider}")
    if provider == "openai":
        print("  (OPENAI_API_KEY detected)")
    elif provider == "anthropic":
        print("  (ANTHROPIC_API_KEY detected)")
    else:
        print("  (No API key found, using local Ollama)")
        print("  Tip: Set OPENAI_API_KEY or ANTHROPIC_API_KEY for faster results")

    results = []

    for url, name in TEST_URLS:
        result = await benchmark_url(url, name, identifier, converter)
        if result:
            results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if results:
        total_tokens = sum(r["skeleton_tokens"] for r in results)
        total_cost = sum(r["cost_usd"] for r in results)
        avg_time = sum(r["time_seconds"] for r in results) / len(results)

        print(f"\nProvider: {identifier._provider}")
        print(f"Pages tested: {len(results)}")
        print(f"Total skeleton tokens: {total_tokens:,}")
        print(f"Total cost: {format_cost(total_cost)}")
        print(f"Average time per page: {avg_time:.2f}s")
        print(f"\nProjected costs:")
        print(f"  100 new domains: {format_cost(total_cost / len(results) * 100)}")
        print(f"  1,000 new domains: {format_cost(total_cost / len(results) * 1000)}")

        # Cache benefit
        print(f"\nCache benefit:")
        print(f"  After first scrape, all subsequent scrapes of same domain = $0")
        print(f"  Selector cache location: {identifier.cache.cache_path}")

    # Show cache stats
    print(f"\nCache stats: {identifier.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
