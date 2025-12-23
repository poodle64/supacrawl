"""HTML to Markdown converter with Firecrawl output parity.

Extraction methods (in priority order):
1. LLM-assisted: Uses cheap LLM to identify main content selector (~$0.00005/domain)
2. Trafilatura: ML-based content extraction (F1=0.958)
3. Pattern matching: CSS selector heuristics (fallback)

The LLM approach is optional and requires Ollama. When enabled, it:
- Extracts a DOM skeleton (~200 tokens)
- Asks a cheap model to identify the main content CSS selector
- Caches the selector per-domain for reuse
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter as BaseMarkdownConverter

LOGGER = logging.getLogger(__name__)

# Try to import trafilatura (optional but recommended)
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    LOGGER.warning("trafilatura not installed, using fallback content extraction")

# LLM content identifier (lazy loaded)
_llm_identifier = None


class AbsoluteUrlConverter(BaseMarkdownConverter):
    """Markdownify converter that resolves relative URLs to absolute."""

    def __init__(self, base_url: str | None = None, **kwargs):
        """Initialize with base URL for resolving relative links."""
        super().__init__(**kwargs)
        self.base_url = base_url

    def convert_a(self, el, text, parent_tags):
        """Convert anchor tags, resolving relative URLs."""
        href = el.get("href", "")
        title = el.get("title", "")

        # Resolve relative URL to absolute
        if href and self.base_url and not urlparse(href).netloc:
            href = urljoin(self.base_url, href)

        if not text.strip():
            return ""

        if title:
            return f'[{text}]({href} "{title}")'
        return f"[{text}]({href})"

    def convert_img(self, el, text, parent_tags):
        """Convert image tags, resolving relative URLs."""
        src = el.get("src", "")
        alt = el.get("alt", "")
        title = el.get("title", "")

        # Resolve relative URL to absolute
        if src and self.base_url and not urlparse(src).netloc:
            src = urljoin(self.base_url, src)

        if not src:
            return ""

        if title:
            return f'![{alt}]({src} "{title}")'
        return f"![{alt}]({src})"


def _get_llm_identifier():
    """Lazy-load the LLM content identifier."""
    global _llm_identifier
    if _llm_identifier is None:
        try:
            from web_scraper.llm_content import LLMContentIdentifier
            _llm_identifier = LLMContentIdentifier()
        except Exception as e:
            LOGGER.debug(f"LLM content identifier not available: {e}")
            _llm_identifier = False  # Mark as unavailable
    return _llm_identifier if _llm_identifier else None


class MarkdownConverter:
    """Convert HTML to Firecrawl-compatible markdown.

    Uses a tiered extraction approach:
    1. LLM-assisted: Identify content selector via cheap LLM (optional, requires Ollama)
    2. Trafilatura: ML-based content extraction (F1=0.958)
    3. Pattern-based: CSS selector heuristics (fallback)

    Usage:
        converter = MarkdownConverter()
        markdown = converter.convert(html, base_url="https://example.com")

        # With LLM assistance (requires Ollama running locally)
        markdown = converter.convert(html, base_url="https://example.com", use_llm=True)
    """

    # Tags to remove completely (for fallback method)
    REMOVE_TAGS = [
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "noscript",
        "iframe",
        "svg",
    ]

    # CSS selectors for boilerplate removal (fallback method)
    # NOTE: These are only used if trafilatura fails
    BOILERPLATE_SELECTORS = [
        # Footer patterns
        "[class*='site-footer']",
        "[id*='site-footer']",
        ".footer",
        "#footer",
        "[role='contentinfo']",
        # Cookie/consent patterns
        "[class*='cookie']",
        "[id*='cookie']",
        "[class*='consent']",
        "[id*='consent']",
        "[class*='gdpr']",
        "[class*='privacy-banner']",
        # Popup/modal patterns
        "[class*='popup']",
        "[class*='modal']",
        "[class*='overlay']",
        # Advertisement patterns
        "[class*='advertisement']",
        "[class*='ad-wrapper']",
        "[class*='sponsored']",
        # Social widgets
        "[class*='social-share']",
        "[class*='share-buttons']",
        # Navigation
        "[role='navigation']",
        ".pagination",
        ".pager",
    ]

    # Main content selectors (fallback method)
    MAIN_CONTENT_SELECTORS = [
        "#mw-content-text",  # Wikipedia
        ".mw-parser-output",
        ".body",  # Sphinx docs
        ".document",
        ".rst-content",
        ".main-page-content",  # MDN
        "main",
        "article",
        "[role='main']",
        "#content",
        "#main",
        ".main-content",
        ".post-content",
        ".article-content",
        ".entry-content",
    ]

    def convert(
        self,
        html: str,
        base_url: str | None = None,
        only_main_content: bool = True,
        remove_boilerplate: bool = True,
        use_llm: bool = False,
    ) -> str:
        """Convert HTML to markdown.

        Uses a tiered extraction approach:
        1. LLM-assisted (if use_llm=True and Ollama available)
        2. Trafilatura ML-based extraction
        3. Pattern-based extraction (fallback)

        Args:
            html: Raw HTML content
            base_url: Base URL for resolving relative links
            only_main_content: Extract main content area only
            remove_boilerplate: Remove nav, footer, ads, etc.
            use_llm: Use LLM to identify main content selector (requires Ollama)

        Returns:
            Clean markdown string
        """
        if not html or not html.strip():
            return ""

        # Try LLM-assisted extraction first (if enabled)
        if use_llm and only_main_content and base_url:
            markdown = self._convert_with_llm(html, base_url)
            if markdown and len(markdown) > 100:
                LOGGER.debug("Used LLM-assisted content extraction")
                return markdown
            LOGGER.debug("LLM extraction returned insufficient content, trying trafilatura")

        # Try trafilatura (ML-based extraction)
        if TRAFILATURA_AVAILABLE and only_main_content:
            markdown = self._convert_with_trafilatura(html, base_url)
            if markdown and len(markdown) > 100:
                LOGGER.debug("Used trafilatura for content extraction")
                return markdown
            LOGGER.debug("Trafilatura returned insufficient content, using fallback")

        # Fallback to pattern-based extraction
        return self._convert_with_patterns(
            html, base_url, only_main_content, remove_boilerplate
        )

    def _convert_with_llm(
        self, html: str, base_url: str
    ) -> str:
        """Extract content using LLM-identified selector.

        Args:
            html: Raw HTML content
            base_url: Page URL (used for domain caching)

        Returns:
            Markdown string or empty if extraction fails
        """
        identifier = _get_llm_identifier()
        if not identifier:
            return ""

        try:
            selector = identifier.identify_selector(html, base_url)
            if not selector:
                return ""

            soup = BeautifulSoup(html, "html.parser")
            element = soup.select_one(selector)
            if not element:
                return ""

            # Convert the identified content to markdown
            converter = AbsoluteUrlConverter(
                base_url=base_url,
                heading_style="atx",
                bullets="-",
                code_language="",
                strip=["script", "style", "nav", "footer", "header"],
                wrap=False,
                wrap_width=0,
            )
            markdown = converter.convert(str(element))
            return self._clean_whitespace(markdown)

        except Exception as e:
            LOGGER.debug(f"LLM-assisted extraction failed: {e}")
            return ""

    def _convert_with_trafilatura(
        self, html: str, base_url: str | None = None
    ) -> str:
        """Extract content using trafilatura's ML-based approach.

        Args:
            html: Raw HTML content
            base_url: Base URL for resolving relative links

        Returns:
            Markdown string or empty if extraction fails
        """
        try:
            # Extract content with trafilatura
            # output_format='markdown' gives us markdown directly
            # include_links=True preserves hyperlinks
            # include_images=True preserves images
            # include_tables=True preserves tables
            result = trafilatura.extract(
                html,
                output_format='markdown',
                include_links=True,
                include_images=True,
                include_tables=True,
                include_comments=False,
                no_fallback=False,  # Use fallback algorithms
                url=base_url,  # For URL resolution
            )

            if result:
                return self._clean_whitespace(result)
            return ""

        except Exception as e:
            LOGGER.debug(f"Trafilatura extraction failed: {e}")
            return ""

    def _convert_with_patterns(
        self,
        html: str,
        base_url: str | None = None,
        only_main_content: bool = True,
        remove_boilerplate: bool = True,
    ) -> str:
        """Extract content using pattern-based approach (fallback).

        Args:
            html: Raw HTML content
            base_url: Base URL for resolving relative links
            only_main_content: Extract main content area only
            remove_boilerplate: Remove nav, footer, ads, etc.

        Returns:
            Markdown string
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            if remove_boilerplate:
                self._remove_boilerplate(soup)

            content_element = None
            if only_main_content:
                content_element = self._find_main_content(soup)

            if content_element:
                html_to_convert = str(content_element)
            else:
                body = soup.find("body")
                html_to_convert = str(body) if body else str(soup)

            converter = AbsoluteUrlConverter(
                base_url=base_url,
                heading_style="atx",
                bullets="-",
                code_language="",
                strip=["script", "style", "nav", "footer", "header"],
                wrap=False,
                wrap_width=0,
            )
            markdown = converter.convert(html_to_convert)

            return self._clean_whitespace(markdown)

        except Exception as e:
            LOGGER.warning(f"Pattern-based conversion failed: {e}")
            try:
                soup = BeautifulSoup(html, "html.parser")
                return soup.get_text(separator="\n\n", strip=True)
            except Exception:
                return ""

    def _remove_boilerplate(self, soup: BeautifulSoup) -> None:
        """Remove boilerplate elements in-place."""
        for tag_name in self.REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        for selector in self.BOILERPLATE_SELECTORS:
            try:
                for element in soup.select(selector):
                    if not self._is_main_content(element):
                        element.decompose()
            except Exception:
                pass

    def _is_main_content(self, element: Tag) -> bool:
        """Check if element is likely main content."""
        if not isinstance(element, Tag):
            return False

        el_id = (element.get("id") or "").lower()
        el_class = " ".join(element.get("class") or []).lower()
        el_role = (element.get("role") or "").lower()

        main_indicators = ["main", "content", "article", "post", "entry"]
        combined = f"{el_id} {el_class} {el_role}"

        return any(indicator in combined for indicator in main_indicators)

    def _find_main_content(self, soup: BeautifulSoup) -> Tag | None:
        """Find the main content element."""
        for selector in self.MAIN_CONTENT_SELECTORS:
            try:
                content_element = soup.select_one(selector)
                if content_element:
                    LOGGER.debug(f"Found main content using selector: {selector}")
                    return content_element
            except Exception:
                pass

        LOGGER.debug("No main content selector matched, using full body")
        return None

    def _clean_whitespace(self, markdown: str) -> str:
        """Clean up excessive whitespace."""
        lines = []
        prev_empty = False

        for line in markdown.splitlines():
            stripped = line.rstrip()
            is_empty = not stripped

            if is_empty:
                if not prev_empty:
                    lines.append("")
                prev_empty = True
            else:
                lines.append(stripped)
                prev_empty = False

        return "\n".join(lines).strip()
