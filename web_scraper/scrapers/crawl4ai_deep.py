"""Deep crawl strategy helpers."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from crawl4ai.deep_crawling import (  # type: ignore[import-untyped]
    BFSDeepCrawlStrategy,
    BestFirstCrawlingStrategy,
    KeywordRelevanceScorer,
)
from crawl4ai.deep_crawling.filters import FilterChain  # type: ignore[import-untyped]

from web_scraper.models import SiteConfig


def build_deep_crawl_strategy(
    config: SiteConfig, filter_chain: FilterChain | None
):
    """Prefer best-first crawling with keyword scoring to stay on-topic."""
    max_depth = estimate_max_depth(config.max_pages)
    keywords = keyword_seeds(config)

    if keywords:
        scorer = KeywordRelevanceScorer(keywords=keywords, weight=0.7)
        return BestFirstCrawlingStrategy(
            max_depth=max_depth,
            include_external=config.include_subdomains,
            filter_chain=filter_chain,
            url_scorer=scorer,
            max_pages=config.max_pages,
        )

    return BFSDeepCrawlStrategy(
        max_depth=max_depth,
        include_external=config.include_subdomains,
        filter_chain=filter_chain,
        max_pages=config.max_pages,
    )


def estimate_max_depth(max_pages: int) -> int:
    """Heuristic depth estimate from max_pages."""
    if max_pages <= 1:
        return 1
    if max_pages <= 10:
        return 2
    if max_pages <= 100:
        return 3
    if max_pages <= 1000:
        return 4
    return 5


def keyword_seeds(config: SiteConfig) -> list[str]:
    """
    Derive lightweight keywords from include patterns and entrypoint paths
    to help the best-first scorer prioritize relevant docs.
    """
    tokens: set[str] = set()
    stopwords = {
        "https",
        "http",
        "www",
        "docs",
        "doc",
        "api",
        "v1",
        "v2",
        "reference",
        "guide",
        "guides",
        "overview",
        "index",
        "html",
    }

    def add_from_url(url: str) -> None:
        parts = urlsplit(url)
        for part in parts.path.split("/"):
            for piece in re.split(r"[-_]", part):
                token = piece.strip().lower()
                if len(token) < 3 or token.isdigit() or token in stopwords:
                    continue
                tokens.add(token)

    for pattern in config.include:
        add_from_url(pattern)
    for entry in config.entrypoints:
        add_from_url(entry)

    # Fall back to id/name keywords
    for val in (config.id, config.name):
        for piece in re.split(r"[\\s/_-]", val):
            token = piece.strip().lower()
            if len(token) > 2 and token not in stopwords:
                tokens.add(token)

    return sorted(tokens)
