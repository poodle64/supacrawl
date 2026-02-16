"""HTML to Markdown converter with high-quality output.

Uses a pure Playwright + markdownify approach:
1. Playwright renders the page fully (JavaScript execution)
2. BeautifulSoup cleans the HTML (removes boilerplate)
3. markdownify converts to markdown (preserves tables and structure)

This approach treats each page like an actual browser, ensuring JavaScript-rendered
content is captured and table structure is preserved.

Site-Specific Preprocessors
===========================
Some documentation frameworks produce HTML that converts poorly to markdown.
We maintain a registry of site-specific preprocessors that improve output quality.

To add a new preprocessor:
1. Create a detection function: _detect_<name>(soup) -> bool
2. Create a handler function: _preprocess_<name>(soup) -> None
3. Register in SITE_PREPROCESSORS with documentation

See SITE_PREPROCESSORS below for the current registry.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter as BaseMarkdownConverter

LOGGER = logging.getLogger(__name__)


# =============================================================================
# Site-Specific Preprocessor Registry
# =============================================================================


@dataclass
class SitePreprocessor:
    """Registration for a site-specific HTML preprocessor.

    Attributes:
        name: Short identifier (e.g., "mkdocs_material")
        description: What this preprocessor handles
        examples: Example sites using this framework
        detect: Function to check if this preprocessor applies
        preprocess: Function to transform the HTML
    """

    name: str
    description: str
    examples: list[str]
    detect: Callable[[BeautifulSoup], bool]
    preprocess: Callable[[BeautifulSoup], None]


def _detect_mkdocs_material(soup: BeautifulSoup) -> bool:
    """Detect if the page is built with MkDocs Material theme.

    Checks for characteristic MkDocs Material markers:
    - md-content class (main content wrapper)
    - data-md-* attributes (Material Design data attributes)
    - Combination of admonition + headerlink classes
    """
    # Check for MkDocs Material specific classes
    if soup.select_one(".md-content, .md-main, [data-md-component]"):
        return True

    # Check for combination of MkDocs-specific elements
    has_headerlinks = bool(soup.select_one("a.headerlink"))
    has_admonitions = bool(soup.select_one("div.admonition"))
    has_tabbed = bool(soup.select_one("div.tabbed-set"))
    has_highlighttable = bool(soup.select_one("table.highlighttable"))

    # If we see multiple MkDocs patterns, it's likely MkDocs
    mkdocs_indicators = sum([has_headerlinks, has_admonitions, has_tabbed, has_highlighttable])
    return mkdocs_indicators >= 2


def _preprocess_mkdocs_material(soup: BeautifulSoup) -> None:
    """Preprocess MkDocs Material HTML for better markdown conversion.

    Handles MkDocs Material-specific elements:
    - Strip permalink anchors from headings (headerlink class)
    - Convert line-numbered code tables to proper code blocks
    - Convert admonitions to blockquotes with bold titles
    - Add clear separators for tabbed content

    Args:
        soup: BeautifulSoup object to modify in-place
    """
    # 1. Strip permalink anchors from headings
    for anchor in soup.select("a.headerlink"):
        anchor.decompose()

    # 2. Convert line-numbered code tables to proper code blocks
    for table in soup.select("table.highlighttable"):
        # Find the code cell
        code_cell = table.select_one("td.code")
        if code_cell:
            # Find the code element
            code_elem = code_cell.select_one("code")
            if code_elem:
                # Get the text content, preserving line breaks
                code_text = code_elem.get_text()

                # Try to detect language from parent class
                lang = ""
                highlight_div = table.find_parent("div", class_="highlight")
                if highlight_div:
                    for cls in highlight_div.get("class", []):
                        # Classes like "language-python" or just language names
                        if cls.startswith("language-"):
                            lang = cls.replace("language-", "")
                            break

                # Create new pre/code structure
                new_pre = soup.new_tag("pre")
                new_code = soup.new_tag("code")
                if lang:
                    new_code["class"] = [f"language-{lang}"]
                new_code.string = code_text
                new_pre.append(new_code)

                # Replace the table with the new pre block
                table.replace_with(new_pre)

    # 3. Convert admonitions to blockquotes with bold titles
    for admonition in soup.select("div.admonition"):
        # Get the type (note, warning, tip, example, etc.)
        admon_type = "Note"
        for cls in admonition.get("class", []):
            if cls != "admonition":
                admon_type = cls.capitalize()
                break

        # Get the title if present
        title_elem = admonition.select_one("p.admonition-title")
        title_text = title_elem.get_text(strip=True) if title_elem else admon_type
        if title_elem:
            title_elem.decompose()

        # Get remaining content
        content_parts = []
        for child in admonition.children:
            if hasattr(child, "get_text"):
                text = child.get_text(strip=True)
                if text:
                    content_parts.append(text)
            elif isinstance(child, str) and child.strip():
                content_parts.append(child.strip())

        content = " ".join(content_parts)

        # Create blockquote with bold title
        blockquote = soup.new_tag("blockquote")
        title_p = soup.new_tag("p")
        strong = soup.new_tag("strong")
        strong.string = f"{title_text}:"
        title_p.append(strong)
        title_p.append(f" {content}")
        blockquote.append(title_p)

        admonition.replace_with(blockquote)

    # 4. Handle tabbed content - add language/tab headers
    for tabbed_set in soup.select("div.tabbed-set"):
        # Get tab labels
        labels = []
        for label_elem in tabbed_set.select("div.tabbed-labels label"):
            label_text = label_elem.get_text(strip=True)
            if label_text:
                labels.append(label_text)

        # Get tab content blocks
        tab_blocks = tabbed_set.select("div.tabbed-block")

        # Create a container for the processed tabs
        container = soup.new_tag("div")

        for i, block in enumerate(tab_blocks):
            # Add a header for each tab
            label = labels[i] if i < len(labels) else f"Tab {i + 1}"
            header = soup.new_tag("h4")
            header.string = label
            container.append(header)

            # Append the block content
            for child in list(block.children):
                container.append(child.extract())

        tabbed_set.replace_with(container)


# =============================================================================
# Preprocessor Registry
# =============================================================================

SITE_PREPROCESSORS: list[SitePreprocessor] = [
    SitePreprocessor(
        name="mkdocs_material",
        description=(
            "MkDocs with Material theme. Handles: permalink anchors in headings, "
            "line-numbered code tables, admonition blocks, tabbed content panels."
        ),
        examples=[
            "help.ctrader.com",
            "fastapi.tiangolo.com",
            "docs.pydantic.dev",
            "squidfunk.github.io/mkdocs-material",
        ],
        detect=_detect_mkdocs_material,
        preprocess=_preprocess_mkdocs_material,
    ),
    # Add new preprocessors here following the same pattern:
    # SitePreprocessor(
    #     name="sphinx_rtd",
    #     description="Sphinx with ReadTheDocs theme. Handles: ...",
    #     examples=["readthedocs.io sites"],
    #     detect=_detect_sphinx_rtd,
    #     preprocess=_preprocess_sphinx_rtd,
    # ),
]


def apply_site_preprocessors(soup: BeautifulSoup) -> list[str]:
    """Apply all matching site-specific preprocessors.

    Iterates through registered preprocessors, detects which ones apply,
    and runs their preprocessing functions.

    Args:
        soup: BeautifulSoup object to preprocess in-place

    Returns:
        List of preprocessor names that were applied
    """
    applied = []
    for preprocessor in SITE_PREPROCESSORS:
        try:
            if preprocessor.detect(soup):
                LOGGER.debug(f"Detected {preprocessor.name}, applying preprocessor")
                preprocessor.preprocess(soup)
                applied.append(preprocessor.name)
        except Exception as e:
            LOGGER.warning(f"Preprocessor {preprocessor.name} failed: {e}")
    return applied


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
        """Convert anchor tags, resolving relative URLs.

        Strips javascript: pseudo-protocol links (UI interactions with no semantic meaning).
        """
        href = el.get("href", "")
        title = el.get("title", "")

        # Clean up text - preserve content even if whitespace-only
        text = text.strip() if text else ""
        if not text:
            # Try to get text from nested elements
            text = el.get_text(strip=True)
        if not text:
            return ""

        # Strip javascript: pseudo-protocol links (case-insensitive) - remove entirely
        # These are UI controls (print, share, etc.) with no semantic content value
        if href.lower().strip().startswith("javascript:"):
            return ""

        # Resolve relative URL to absolute
        if href and self.base_url and not urlparse(href).netloc:
            href = urljoin(self.base_url, href)

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
    """Convert HTML to clean markdown.

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
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> str:
        """Convert HTML to markdown.

        Uses markdownify for conversion, which preserves table structure correctly.

        Args:
            html: Raw HTML content (should be post-JavaScript rendering from Playwright)
            base_url: Base URL for resolving relative links
            only_main_content: Extract main content area only
            remove_boilerplate: Remove nav, footer, ads, etc.
            include_tags: CSS selectors for elements to include.
                         When specified, takes precedence over only_main_content.
            exclude_tags: CSS selectors for elements to exclude.
                         Applied before include_tags filtering.

        Returns:
            Clean markdown string
        """
        if not html or not html.strip():
            return ""

        return self._convert_with_patterns(
            html, base_url, only_main_content, remove_boilerplate, include_tags, exclude_tags
        )

    def _convert_with_patterns(
        self,
        html: str,
        base_url: str | None = None,
        only_main_content: bool = True,
        remove_boilerplate: bool = True,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> str:
        """Extract content using pattern-based approach (fallback).

        Args:
            html: Raw HTML content
            base_url: Base URL for resolving relative links
            only_main_content: Extract main content area only
            remove_boilerplate: Remove nav, footer, ads, etc.
            include_tags: CSS selectors for elements to include
            exclude_tags: CSS selectors for elements to exclude

        Returns:
            Markdown string
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            if remove_boilerplate:
                self._remove_boilerplate(soup)

            # Apply site-specific preprocessors (auto-detected)
            apply_site_preprocessors(soup)

            # Apply exclude_tags first (before include_tags)
            if exclude_tags:
                self._apply_exclude_tags(soup, exclude_tags)

            content_element = None

            # include_tags takes precedence over only_main_content
            if include_tags:
                content_element = self._apply_include_tags(soup, include_tags)
            elif only_main_content:
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

    def _apply_exclude_tags(self, soup: BeautifulSoup, exclude_tags: list[str]) -> None:
        """Remove elements matching exclude_tags selectors.

        Args:
            soup: BeautifulSoup object to modify in-place
            exclude_tags: List of CSS selectors for elements to remove
        """
        for selector in exclude_tags:
            try:
                for element in soup.select(selector):
                    element.decompose()
            except Exception as e:
                LOGGER.warning(f"Invalid exclude_tags selector '{selector}': {e}")

    def _apply_include_tags(self, soup: BeautifulSoup, include_tags: list[str]) -> Tag | None:
        """Extract only elements matching include_tags selectors.

        Args:
            soup: BeautifulSoup object to search
            include_tags: List of CSS selectors for elements to include

        Returns:
            A wrapper Tag containing all matched elements, or None if no matches
        """
        matched_elements: list[Tag] = []

        for selector in include_tags:
            try:
                for element in soup.select(selector):
                    # Avoid duplicates (e.g., nested matches)
                    if element not in matched_elements:
                        matched_elements.append(element)
            except Exception as e:
                LOGGER.warning(f"Invalid include_tags selector '{selector}': {e}")

        if not matched_elements:
            LOGGER.debug("No elements matched include_tags selectors")
            return None

        # Create a wrapper div to hold all matched elements
        wrapper = soup.new_tag("div")
        for element in matched_elements:
            # Copy the element to avoid modifying the original structure
            wrapper.append(element.extract())

        LOGGER.debug(f"include_tags matched {len(matched_elements)} elements")
        return wrapper

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
