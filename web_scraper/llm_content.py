"""LLM-assisted content identification for web scraping.

Uses a cheap LLM to identify the main content element from a DOM skeleton,
enabling accurate content extraction with minimal token usage.

Approach:
1. Extract DOM skeleton (~200 tokens) showing structure only
2. Ask LLM to identify main content CSS selector
3. Cache selector per-domain for reuse
4. Use selector for content extraction

Token efficiency:
- Input: ~200 tokens (DOM skeleton)
- Output: ~10 tokens (CSS selector)
- Cost: ~$0.00005 per new domain (using GPT-4o-mini or Haiku)
- Cached domains: $0

Supported providers (in order of preference):
1. OpenAI (OPENAI_API_KEY) - uses gpt-4o-mini
2. Anthropic (ANTHROPIC_API_KEY) - uses claude-3-haiku
3. Ollama (local, no API key) - uses llama3.2:1b

Set the appropriate environment variable to enable a provider.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

LOGGER = logging.getLogger(__name__)

# Default cache location
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "web-scraper" / "selectors.json"

# System prompt for selector identification
SELECTOR_SYSTEM_PROMPT = """You are a web content extraction expert. Given a DOM skeleton showing the structure of a web page, identify the CSS selector for the main content element.

Rules:
1. Return ONLY the CSS selector, nothing else - no explanation, no markdown
2. Prefer semantic selectors: main, article, [role="main"], #content
3. Look for patterns like: main-content, article-content, post-content, entry-content
4. Avoid navigation, header, footer, sidebar elements
5. If multiple candidates exist, choose the most specific one
6. The selector should work with document.querySelector()

Examples of good responses (just the selector, nothing else):
main#content
article.post-content
div.main-content
[role="main"]
#mw-content-text"""


class DOMSkeleton:
    """Extract structural skeleton from HTML for LLM analysis."""

    # Tags to skip entirely
    SKIP_TAGS = frozenset([
        "script", "style", "noscript", "svg", "path", "link", "meta",
        "head", "template", "slot", "iframe", "canvas", "video", "audio"
    ])

    # Tags that are structural but we want to show
    STRUCTURAL_TAGS = frozenset([
        "html", "body", "div", "section", "article", "main", "aside",
        "header", "footer", "nav", "form", "table", "ul", "ol", "dl"
    ])

    def __init__(self, html: str):
        """Initialize with HTML content."""
        self.soup = BeautifulSoup(html, "html.parser")

    def extract(self, max_depth: int = 3) -> str:
        """Extract DOM skeleton as indented text.

        Args:
            max_depth: Maximum depth to traverse (default 3)

        Returns:
            Indented text representation of DOM structure
        """
        body = self.soup.find("body")
        if not body:
            return ""

        lines: list[str] = []
        self._traverse(body, 0, max_depth, lines)
        return "\n".join(lines)

    def _traverse(
        self,
        element: Tag,
        depth: int,
        max_depth: int,
        lines: list[str]
    ) -> None:
        """Recursively traverse DOM and build skeleton."""
        if depth > max_depth:
            return

        if not isinstance(element, Tag):
            return

        if element.name in self.SKIP_TAGS:
            return

        # Build node representation
        node = self._format_node(element)
        indent = "  " * depth
        lines.append(f"{indent}{node}")

        # Process children
        for child in element.children:
            if isinstance(child, Tag):
                self._traverse(child, depth + 1, max_depth, lines)

    def _format_node(self, element: Tag) -> str:
        """Format a single DOM node for display."""
        parts = [element.name]

        # Add id
        el_id = element.get("id", "")
        if el_id:
            parts.append(f"#{el_id}")

        # Add first 2 classes
        el_classes = element.get("class", [])
        if el_classes:
            for cls in el_classes[:2]:
                parts.append(f".{cls}")

        # Add role attribute
        el_role = element.get("role", "")
        if el_role:
            parts.append(f"[role={el_role}]")

        return "".join(parts)


class SelectorCache:
    """Cache for domain-to-selector mappings."""

    def __init__(self, cache_path: Path | None = None):
        """Initialize cache.

        Args:
            cache_path: Path to cache file (default ~/.cache/web-scraper/selectors.json)
        """
        self.cache_path = cache_path or DEFAULT_CACHE_PATH
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text())
                LOGGER.debug(f"Loaded {len(self._cache)} cached selectors")
            except (json.JSONDecodeError, OSError) as e:
                LOGGER.warning(f"Failed to load selector cache: {e}")
                self._cache = {}

    def _save(self) -> None:
        """Save cache to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, indent=2))
        except OSError as e:
            LOGGER.warning(f"Failed to save selector cache: {e}")

    def get(self, domain: str) -> str | None:
        """Get cached selector for domain."""
        return self._cache.get(domain)

    def set(self, domain: str, selector: str) -> None:
        """Cache selector for domain."""
        self._cache[domain] = selector
        self._save()

    def clear(self) -> None:
        """Clear all cached selectors."""
        self._cache = {}
        self._save()


class LLMContentIdentifier:
    """Use LLM to identify main content element from DOM skeleton.

    Supports multiple providers:
    - OpenAI (set OPENAI_API_KEY)
    - Anthropic (set ANTHROPIC_API_KEY)
    - Ollama (local, no API key needed)
    """

    def __init__(
        self,
        provider: str | None = None,
        cache_path: Path | None = None
    ):
        """Initialize the content identifier.

        Args:
            provider: Force a specific provider ('openai', 'anthropic', 'ollama').
                     If None, auto-detects based on available API keys.
            cache_path: Path to selector cache file
        """
        self.cache = SelectorCache(cache_path)
        self._provider = provider or self._detect_provider()
        self._client = None

    def _detect_provider(self) -> str:
        """Detect the best available LLM provider."""
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        return "ollama"

    def _get_openai_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except ImportError:
                raise ImportError("openai package required. Install with: pip install openai")
        return self._client

    def _get_anthropic_client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic()
            except ImportError:
                raise ImportError("anthropic package required. Install with: pip install anthropic")
        return self._client

    def identify_selector(
        self,
        html: str,
        url: str,
        use_cache: bool = True
    ) -> str | None:
        """Identify the main content selector for a page.

        Args:
            html: Raw HTML content
            url: Page URL (used for domain caching)
            use_cache: Whether to use cached selectors (default True)

        Returns:
            CSS selector string, or None if identification failed
        """
        # Extract domain for caching
        domain = urlparse(url).netloc

        # Check cache first
        if use_cache:
            cached = self.cache.get(domain)
            if cached:
                LOGGER.debug(f"Using cached selector for {domain}: {cached}")
                return cached

        # Extract DOM skeleton
        skeleton = DOMSkeleton(html).extract(max_depth=3)
        if not skeleton:
            LOGGER.warning("Failed to extract DOM skeleton")
            return self._heuristic_selector(html)

        # Query LLM based on provider
        selector = self._query_llm(skeleton)
        if selector:
            # Validate selector works
            soup = BeautifulSoup(html, "html.parser")
            try:
                element = soup.select_one(selector)
                if element:
                    # Cache successful selector
                    self.cache.set(domain, selector)
                    LOGGER.info(f"Identified selector for {domain}: {selector}")
                    return selector
                else:
                    LOGGER.warning(f"LLM selector '{selector}' didn't match any elements")
            except Exception as e:
                LOGGER.warning(f"Invalid selector '{selector}': {e}")

        # Fall back to heuristics
        return self._heuristic_selector(html)

    def _query_llm(self, skeleton: str) -> str | None:
        """Query LLM to identify content selector."""
        try:
            if self._provider == "openai":
                return self._query_openai(skeleton)
            elif self._provider == "anthropic":
                return self._query_anthropic(skeleton)
            else:
                return self._query_ollama(skeleton)
        except Exception as e:
            LOGGER.error(f"LLM query failed ({self._provider}): {e}")
            return None

    def _query_openai(self, skeleton: str) -> str | None:
        """Query OpenAI API."""
        client = self._get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SELECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": f"DOM skeleton:\n{skeleton}"}
            ],
            temperature=0,
            max_tokens=50,
        )
        return self._clean_selector(response.choices[0].message.content)

    def _query_anthropic(self, skeleton: str) -> str | None:
        """Query Anthropic API."""
        client = self._get_anthropic_client()
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=50,
            system=SELECTOR_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"DOM skeleton:\n{skeleton}"}
            ],
        )
        return self._clean_selector(response.content[0].text)

    def _query_ollama(self, skeleton: str) -> str | None:
        """Query local Ollama instance."""
        try:
            import ollama
        except ImportError:
            LOGGER.warning("ollama package not installed")
            return None

        try:
            response = ollama.chat(
                model="llama3.2:1b",
                messages=[
                    {"role": "system", "content": SELECTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": f"DOM skeleton:\n{skeleton}"}
                ],
                options={
                    "temperature": 0,
                    "num_predict": 50,
                }
            )
            return self._clean_selector(response["message"]["content"])
        except Exception as e:
            LOGGER.warning(f"Ollama query failed: {e}")
            return None

    def _clean_selector(self, raw: str | None) -> str | None:
        """Clean up LLM response to extract just the selector."""
        if not raw:
            return None

        selector = raw.strip()

        # Remove markdown code blocks
        selector = selector.strip("`'\"")
        if selector.startswith("css\n"):
            selector = selector[4:]
        if selector.startswith("```"):
            selector = selector.split("\n")[1] if "\n" in selector else selector[3:]

        # If it looks like just a selector (no spaces except in attribute selectors)
        if selector and (
            selector.startswith(".")
            or selector.startswith("#")
            or selector.startswith("[")
            or selector in ("main", "article", "section")
            or not any(c in selector for c in [" ", "The", "I "])
        ):
            return selector.split("\n")[0].strip()

        # Try to extract selector from explanation
        lines = selector.split("\n")
        for line in lines:
            line = line.strip().strip("`'\"")
            # Skip explanation lines
            if line and not any(line.startswith(skip) for skip in ["The", "I ", "Based", "This"]):
                # Check if it looks like a selector
                if line.startswith((".", "#", "[", "main", "article", "div", "section")):
                    return line

        return None

    def _heuristic_selector(self, html: str) -> str | None:
        """Fall back to heuristic selector identification."""
        soup = BeautifulSoup(html, "html.parser")

        # Priority order of selectors to try
        candidates = [
            "main[role=main]",
            "main#content",
            "main.content",
            "main",
            "article.post-content",
            "article.entry-content",
            "article.content",
            "article",
            "[role=main]",
            "#main-content",
            "#content",
            ".main-content",
            ".post-content",
            ".article-content",
            ".entry-content",
            "#mw-content-text",  # Wikipedia
            ".markdown-body",  # GitHub
        ]

        for selector in candidates:
            try:
                element = soup.select_one(selector)
                if element:
                    # Check it has meaningful content
                    text = element.get_text(strip=True)
                    if len(text) > 100:
                        LOGGER.debug(f"Heuristic selector matched: {selector}")
                        return selector
            except Exception:
                continue

        return None

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "cached_domains": len(self.cache._cache),
            "cache_path": str(self.cache.cache_path),
            "provider": self._provider,
        }


def extract_with_llm_selector(
    html: str,
    url: str,
    identifier: LLMContentIdentifier | None = None
) -> str | None:
    """Extract main content using LLM-identified selector.

    Args:
        html: Raw HTML content
        url: Page URL
        identifier: Optional LLMContentIdentifier instance (creates one if not provided)

    Returns:
        Extracted HTML content, or None if extraction failed
    """
    if identifier is None:
        identifier = LLMContentIdentifier()

    selector = identifier.identify_selector(html, url)
    if not selector:
        return None

    soup = BeautifulSoup(html, "html.parser")
    try:
        element = soup.select_one(selector)
        if element:
            return str(element)
    except Exception as e:
        LOGGER.warning(f"Failed to extract with selector '{selector}': {e}")

    return None
