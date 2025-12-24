"""HTML to Markdown converter with Firecrawl output parity.

Uses a pure Playwright + markdownify approach:
1. Playwright renders the page fully (JavaScript execution)
2. BeautifulSoup cleans the HTML (removes boilerplate)
3. markdownify converts to markdown (preserves tables and structure)

This approach treats each page like an actual browser, ensuring JavaScript-rendered
content is captured and table structure is preserved.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter as BaseMarkdownConverter

LOGGER = logging.getLogger(__name__)


class AbsoluteUrlConverter(BaseMarkdownConverter):
    """Markdownify converter that resolves relative URLs to absolute.

    Key features:
    - Resolves relative URLs to absolute
    - Preserves table structure with proper markdown formatting
    - Handles links inside table cells correctly
    """

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

        # Clean up text - preserve content even if whitespace-only
        text = text.strip() if text else ""
        if not text:
            # Try to get text from nested elements
            text = el.get_text(strip=True)
        if not text:
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


class MarkdownConverter:
    """Convert HTML to Firecrawl-compatible markdown.

    Uses a pure Playwright + markdownify approach that preserves table structure
    and handles JavaScript-rendered content properly.

    The extraction process:
    1. Clean HTML by removing boilerplate (scripts, styles, nav, footer, etc.)
    2. Find main content area using CSS selectors
    3. Convert to markdown using markdownify (preserves tables)

    Usage:
        converter = MarkdownConverter()
        markdown = converter.convert(html, base_url="https://example.com")
    """

    # Tags to remove completely
    REMOVE_TAGS = [
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "path",
        "canvas",
        "video",
        "audio",
        "source",
        "track",
        "embed",
        "object",
        "param",
        "template",
    ]

    # Tags to remove only when cleaning for main content
    BOILERPLATE_TAGS = [
        "nav",
        "footer",
        "header",
        "aside",
    ]

    # CSS selectors for boilerplate removal
    BOILERPLATE_SELECTORS = [
        # Navigation patterns
        "[role='navigation']",
        "[role='banner']",
        "[role='contentinfo']",
        ".navigation",
        ".nav-menu",
        ".navbar",
        ".menu",
        ".sidebar",
        ".toc",
        ".table-of-contents",
        # Footer patterns
        "[class*='site-footer']",
        "[id*='site-footer']",
        ".footer",
        "#footer",
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
        "[class*='promo']",
        # Social widgets
        "[class*='social-share']",
        "[class*='share-buttons']",
        "[class*='social-links']",
        # Tracking pixels and hidden elements
        "img[width='1']",
        "img[height='1']",
        "[style*='display:none']",
        "[style*='display: none']",
        "[hidden]",
        ".hidden",
        # Related/recommended content
        "[class*='related-']",
        "[class*='recommended']",
        "[class*='also-read']",
        # Comments sections
        "[class*='comment']",
        "#comments",
        ".disqus",
    ]

    # Main content selectors (in priority order)
    MAIN_CONTENT_SELECTORS = [
        # Framework-specific
        "#mw-content-text",  # Wikipedia
        ".mw-parser-output",
        ".rst-content",  # ReadTheDocs
        ".document",  # Sphinx
        ".markdown-body",  # GitHub
        ".notion-page-content",  # Notion
        # Facebook/Meta developer docs
        "#documentation_body_pagelet",  # Facebook docs main content
        "._4-u2",  # Facebook docs content wrapper
        # Semantic elements
        "main[role='main']",
        "main#content",
        "main.content",
        "main",
        "article.post-content",
        "article.entry-content",
        "article.content",
        "article",
        "[role='main']",
        # Common ID patterns
        "#main-content",
        "#content",
        "#main",
        "#article",
        "#post",
        # Common class patterns
        ".main-content",
        ".content",
        ".post-content",
        ".article-content",
        ".entry-content",
        ".page-content",
        ".body-content",
    ]

    def convert(
        self,
        html: str,
        base_url: str | None = None,
        only_main_content: bool = True,
        remove_boilerplate: bool = True,
    ) -> str:
        """Convert HTML to markdown.

        Uses markdownify for conversion, which preserves table structure correctly.

        Args:
            html: Raw HTML content (should be post-JavaScript rendering from Playwright)
            base_url: Base URL for resolving relative links
            only_main_content: Extract main content area only
            remove_boilerplate: Remove nav, footer, ads, etc.

        Returns:
            Clean markdown string
        """
        if not html or not html.strip():
            return ""

        return self._convert_with_patterns(
            html, base_url, only_main_content, remove_boilerplate
        )

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
        # Remove always-unwanted tags (scripts, styles, etc.)
        for tag_name in self.REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Remove structural boilerplate (nav, footer, etc.)
        for tag_name in self.BOILERPLATE_TAGS:
            for tag in soup.find_all(tag_name):
                # Don't remove if it's the main content area
                if not self._is_main_content(tag):
                    tag.decompose()

        # Remove elements matching boilerplate CSS selectors
        for selector in self.BOILERPLATE_SELECTORS:
            try:
                for element in soup.select(selector):
                    if not self._is_main_content(element):
                        element.decompose()
            except Exception:
                pass

    def _is_main_content(self, element) -> bool:
        """Check if element is likely main content."""
        if element is None or not isinstance(element, Tag):
            return False

        try:
            el_id = (element.get("id") or "").lower()
            el_class = " ".join(element.get("class") or []).lower()
            el_role = (element.get("role") or "").lower()

            main_indicators = ["main", "content", "article", "post", "entry"]
            combined = f"{el_id} {el_class} {el_role}"

            return any(indicator in combined for indicator in main_indicators)
        except Exception:
            return False

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
