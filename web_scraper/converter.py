"""HTML to Markdown converter with Firecrawl output parity."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

LOGGER = logging.getLogger(__name__)


class MarkdownConverter:
    """Convert HTML to Firecrawl-compatible markdown.

    Usage:
        converter = MarkdownConverter()
        markdown = converter.convert(html)
    """

    # Tags to remove completely
    REMOVE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "iframe", "svg"]

    # Selectors to try for main content (in order)
    MAIN_CONTENT_SELECTORS = [
        "main",
        "article",
        "[role='main']",
        ".content",
        "#content",
        ".main-content",
        ".post-content",
        ".article-content",
    ]

    def convert(
        self,
        html: str,
        only_main_content: bool = True,
        remove_boilerplate: bool = True,
    ) -> str:
        """Convert HTML to markdown.

        Args:
            html: Raw HTML content
            only_main_content: Extract main content area only
            remove_boilerplate: Remove nav, footer, ads, etc.

        Returns:
            Clean markdown string
        """
        if not html or not html.strip():
            return ""

        try:
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Remove boilerplate tags if requested
            if remove_boilerplate:
                self._remove_boilerplate(soup)

            # Find main content if requested
            content_element = None
            if only_main_content:
                content_element = self._find_main_content(soup)

            # Use main content or fall back to body
            if content_element:
                html_to_convert = str(content_element)
            else:
                body = soup.find("body")
                html_to_convert = str(body) if body else str(soup)

            # Convert to markdown with markdownify
            # Options match Firecrawl-style output
            markdown = md(
                html_to_convert,
                heading_style="atx",      # Use # style headings
                bullets="-",              # Use - for unordered lists
                code_language="",         # Don't assume language for code blocks
                strip=["script", "style", "nav", "footer", "header"],
                wrap=False,               # Don't wrap lines
                wrap_width=0,             # No line width limit
            )

            # Clean up whitespace
            return self._clean_whitespace(markdown)

        except Exception as e:
            LOGGER.warning(f"Markdown conversion failed: {e}")
            # Fallback: extract text from HTML
            try:
                soup = BeautifulSoup(html, "html.parser")
                return soup.get_text(separator="\n\n", strip=True)
            except Exception:
                return ""

    def _remove_boilerplate(self, soup: BeautifulSoup) -> None:
        """Remove boilerplate elements in-place.

        Args:
            soup: BeautifulSoup object to modify
        """
        for tag_name in self.REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

    def _find_main_content(self, soup: BeautifulSoup) -> Tag | None:
        """Find the main content element.

        Args:
            soup: BeautifulSoup object to search

        Returns:
            Main content Tag or None if not found
        """
        for selector in self.MAIN_CONTENT_SELECTORS:
            content_element = soup.select_one(selector)
            if content_element:
                LOGGER.debug(f"Found main content using selector: {selector}")
                return content_element

        LOGGER.debug("No main content selector matched, using full body")
        return None

    def _clean_whitespace(self, markdown: str) -> str:
        """Clean up excessive whitespace.

        Args:
            markdown: Markdown string to clean

        Returns:
            Cleaned markdown string
        """
        # Strip trailing whitespace per line and collapse multiple blank lines
        lines = []
        prev_empty = False

        for line in markdown.splitlines():
            stripped = line.rstrip()
            is_empty = not stripped

            # Collapse multiple empty lines to at most 2
            if is_empty:
                if not prev_empty:
                    lines.append("")
                prev_empty = True
            else:
                lines.append(stripped)
                prev_empty = False

        # Join lines and strip leading/trailing whitespace from document
        return "\n".join(lines).strip()
