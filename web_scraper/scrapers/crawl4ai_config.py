"""Crawl4AI configuration builders (browser, LLM, markdown, cache)."""

from __future__ import annotations

import logging
import os
from typing import Any

from crawl4ai import (  # type: ignore[import-untyped]
    BrowserConfig,
    CacheMode,
    DefaultMarkdownGenerator,
    LLMConfig,
    ProxyConfig,
)
from crawl4ai.content_filter_strategy import (  # type: ignore[import-untyped]
    BM25ContentFilter,
    LLMContentFilter,
    PruningContentFilter,
)

from web_scraper.models import SiteConfig
from web_scraper.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


def env_true(key: str, default: bool = False) -> bool:
    """Return True when env var represents a truthy value."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_browser_config() -> BrowserConfig:
    """Build a browser config tuned for quality + resilience (stealth, UA rotation)."""
    headless = env_true("CRAWL4AI_HEADLESS", True)
    viewport_width = int(os.getenv("CRAWL4AI_VIEWPORT_WIDTH", "1280"))
    viewport_height = int(os.getenv("CRAWL4AI_VIEWPORT_HEIGHT", "720"))

    proxy_server = os.getenv("CRAWL4AI_PROXY")
    proxy_config = ProxyConfig(server=proxy_server) if proxy_server else None

    user_agent = os.getenv(
        "CRAWL4AI_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    accept_language = os.getenv("CRAWL4AI_ACCEPT_LANGUAGE", "en-US,en;q=0.8")
    headers = {
        "Accept-Language": accept_language,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    return BrowserConfig(
        browser_type=os.getenv("CRAWL4AI_BROWSER_TYPE", "chromium"),
        headless=headless,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        enable_stealth=True,
        user_agent=user_agent,
        user_agent_mode="fixed",
        text_mode=False,
        use_managed_browser=env_true("CRAWL4AI_USE_MANAGED_BROWSER", False),
        user_data_dir=os.getenv("CRAWL4AI_USER_DATA_DIR"),
        proxy_config=proxy_config,
        verbose=env_true("CRAWL4AI_BROWSER_VERBOSE", False),
        headers=headers,
    )


def build_llm_config(correlation_id: str) -> LLMConfig | None:
    """
    Build LLMConfig for the configured provider.

    Order of precedence:
    1. Explicit provider env (CRAWL4AI_LLM_PROVIDER, token/base URL optional)
    2. Ollama toggle (CRAWL4AI_USE_OLLAMA=true)
    """
    provider = os.getenv("CRAWL4AI_LLM_PROVIDER")
    base_url = os.getenv("CRAWL4AI_LLM_BASE_URL")
    api_token = os.getenv("CRAWL4AI_LLM_API_TOKEN")

    # Legacy / default: enable Ollama when toggled
    if not provider and env_true("CRAWL4AI_USE_OLLAMA", False):
        provider = f"ollama/{os.getenv('OLLAMA_MODEL', 'llama3.2')}"
        base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        api_token = None

    if not provider:
        return None

    try:
        backoff_base = float(os.getenv("CRAWL4AI_LLM_BACKOFF_BASE", "2"))
        backoff_max_attempts = int(os.getenv("CRAWL4AI_LLM_BACKOFF_MAX_ATTEMPTS", "3"))
        backoff_factor = float(os.getenv("CRAWL4AI_LLM_BACKOFF_FACTOR", "2"))

        llm_config = LLMConfig(
            provider=provider,
            base_url=base_url,
            api_token=api_token if api_token else None,
            backoff_base_delay=backoff_base,
            backoff_max_attempts=backoff_max_attempts,
            backoff_exponential_factor=backoff_factor,
        )

        log_with_correlation(
            LOGGER,
            logging.INFO,
            "Configured Crawl4AI LLM provider",
            correlation_id=correlation_id,
            provider=provider,
            base_url=base_url or "default",
        )
        return llm_config
    except Exception as exc:
        log_with_correlation(
            LOGGER,
            logging.WARNING,
            f"Failed to configure LLM provider, continuing without LLM: {exc}",
            correlation_id=correlation_id,
            error=str(exc),
        )
        return None


def extract_keywords_from_config(config: SiteConfig) -> str | None:
    """
    Extract keywords from site configuration for BM25 content filtering.

    Args:
        config: Site configuration to extract keywords from.

    Returns:
        Keyword string derived from config name and entrypoints, or None if insufficient.
    """
    keywords_parts: list[str] = []

    # Extract keywords from site name
    if config.name:
        # Simple keyword extraction: split on common separators and take meaningful words
        name_words = [
            word.lower()
            for word in config.name.replace("-", " ").replace("_", " ").split()
            if len(word) > 3 and word.isalnum()
        ]
        keywords_parts.extend(name_words[:3])  # Limit to top 3 words

    # Extract domain keywords from entrypoints
    if config.entrypoints:
        for entrypoint in config.entrypoints[:2]:  # Limit to first 2 entrypoints
            try:
                from urllib.parse import urlparse

                parsed = urlparse(entrypoint)
                domain = parsed.netloc.replace("www.", "").split(".")[0]
                if len(domain) > 3:
                    keywords_parts.append(domain.lower())
            except Exception:
                pass

    if not keywords_parts:
        return None

    # Return unique keywords as space-separated string
    return " ".join(dict.fromkeys(keywords_parts))  # Preserves order, removes duplicates


def build_markdown_generator(
    llm_config: LLMConfig | None,
    correlation_id: str,
    config: SiteConfig | None = None,
) -> DefaultMarkdownGenerator:
    """
    Configure markdown generation for fidelity (tables, links, citations).

    Uses content filters to remove boilerplate (PruningContentFilter by default).
    Optionally enables LLMContentFilter when CRAWL4AI_LLM_FILTER=true.
    """
    options: dict[str, Any] = {
        "body_width": 0,  # keep tables/code intact
        "ignore_links": False,
        "ignore_images": False,
        "single_line_break": True,
    }

    # Build content filter (non-LLM) for boilerplate removal
    content_filter: PruningContentFilter | BM25ContentFilter | None = None
    content_filter_type = os.getenv("CRAWL4AI_CONTENT_FILTER", "pruning").lower()

    if content_filter_type == "none":
        content_filter = None
    elif content_filter_type == "bm25" and config:
        # Use BM25 filter when query keywords are available
        keywords = extract_keywords_from_config(config)
        if keywords:
            bm25_threshold = float(os.getenv("CRAWL4AI_BM25_THRESHOLD", "1.2"))
            try:
                content_filter = BM25ContentFilter(
                    user_query=keywords,
                    bm25_threshold=bm25_threshold,
                    language="en",
                )
                log_with_correlation(
                    LOGGER,
                    logging.INFO,
                    "Enabled BM25 content filter for markdown generation",
                    correlation_id=correlation_id,
                    keywords=keywords,
                    threshold=bm25_threshold,
                )
            except Exception as exc:
                log_with_correlation(
                    LOGGER,
                    logging.WARNING,
                    f"Failed to enable BM25 content filter, falling back to pruning: {exc}",
                    correlation_id=correlation_id,
                    error=str(exc),
                )
                content_filter = None

    # Default to PruningContentFilter if no filter set yet
    if content_filter is None and content_filter_type != "none":
        threshold = float(os.getenv("CRAWL4AI_PRUNING_THRESHOLD", "0.5"))
        threshold_type = os.getenv("CRAWL4AI_PRUNING_THRESHOLD_TYPE", "dynamic")
        # Lower min_word_threshold to preserve headings (headings are typically short)
        # Use 1 to ensure headings are preserved even if they're single words
        min_word_threshold = int(os.getenv("CRAWL4AI_PRUNING_MIN_WORDS", "1"))
        try:
            content_filter = PruningContentFilter(
                threshold=threshold,
                threshold_type=threshold_type,  # type: ignore[arg-type]
                min_word_threshold=min_word_threshold,
            )
            log_with_correlation(
                LOGGER,
                logging.INFO,
                "Enabled PruningContentFilter for markdown generation",
                correlation_id=correlation_id,
                threshold=threshold,
                threshold_type=threshold_type,
            )
        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Failed to enable PruningContentFilter: {exc}",
                correlation_id=correlation_id,
                error=str(exc),
            )

    # LLM content filter (optional, works alongside content filter)
    llm_content_filter = None
    if llm_config and env_true("CRAWL4AI_LLM_FILTER", False):
        instruction = os.getenv(
            "CRAWL4AI_LLM_FILTER_INSTRUCTION",
            (
                "Extract main documentation content. Keep: headings, code blocks, tables, "
                "parameter lists, examples, API references. Remove: navigation menus, "
                "footers, cookie banners, advertisements, social media widgets, related "
                "articles, site navigation, breadcrumbs."
            ),
        )
        chunk_token_threshold = int(os.getenv("CRAWL4AI_LLM_FILTER_CHUNK_TOKENS", "1000"))
        try:
            llm_content_filter = LLMContentFilter(
                llm_config=llm_config,
                instruction=instruction,
                chunk_token_threshold=chunk_token_threshold,
                verbose=env_true("CRAWL4AI_LLM_FILTER_VERBOSE", False),
            )
            log_with_correlation(
                LOGGER,
                logging.INFO,
                "Enabled LLM content filter for markdown generation",
                correlation_id=correlation_id,
                provider=llm_config.provider,
            )
        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Failed to enable LLM content filter: {exc}",
                correlation_id=correlation_id,
                error=str(exc),
            )

    # LLM filter takes precedence if both are enabled (it's more sophisticated)
    final_filter = llm_content_filter if llm_content_filter else content_filter

    return DefaultMarkdownGenerator(content_filter=final_filter, options=options)


def cache_mode() -> CacheMode:
    """Default to BYPASS for freshness; enable cache via env when sources are stable."""
    return CacheMode.ENABLED if env_true("CRAWL4AI_CACHE_ENABLED", False) else CacheMode.BYPASS
