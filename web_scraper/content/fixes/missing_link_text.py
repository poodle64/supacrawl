"""Fix for missing link text in nested strong+link structures.

WORKAROUND: This fix addresses cases where Crawl4AI's markdown extraction misses
link text in nested structures like <strong><a>text</a></strong>, producing
markdown like "* is where you will find..." instead of "* **The [V2 API](url)** is where...".

Upstream issue: Crawl4AI markdown extraction doesn't always preserve link text
in nested formatting structures.

This fix can be enabled/disabled via site configuration (markdown_fixes section).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from web_scraper.content.fixes.base import MarkdownFix
from web_scraper.content.fixes.registry import register_fix


class MissingLinkTextFix(MarkdownFix):
    """Fix missing link text in list items that start with verbs."""

    @property
    def name(self) -> str:
        return "missing-link-text-in-lists"

    @property
    def description(self) -> str:
        return "Injects missing link text in list items that start with verbs (e.g., 'is where...' -> '**The [V2 API](url)** is where...')"

    @property
    def issue_pattern(self) -> str:
        return "List items starting with verbs (is, are, endpoints) that are missing link text at the beginning"

    @property
    def upstream_issue(self) -> str:
        return "Crawl4AI markdown extraction misses link text in nested <strong><a> structures"

    @property
    def enabled(self) -> bool:
        """Always enabled if markdown_fixes.enabled is true in config."""
        return True

    def fix(self, markdown: str, html: str) -> str:
        """
        Fix missing link text by checking HTML for nested strong+link structures.

        Args:
            markdown: Markdown content
            html: HTML content to reference

        Returns:
            Fixed markdown
        """
        try:
            # Quick check: only process if we have lines that might need fixing
            lines = markdown.splitlines()
            needs_fixing = False
            for line in lines:
                stripped = line.strip()
                if (stripped.startswith("- ") or stripped.startswith("* ")) and stripped.lower().startswith(
                    ("- is ", "* is ", "- are ", "* are ", "- endpoints ", "* endpoints ")
                ):
                    needs_fixing = True
                    break

            # Early exit if no lines need fixing
            if not needs_fixing:
                return markdown

            # Limit HTML size to prevent performance issues (1MB max)
            if len(html) > 1_000_000:
                return markdown

            # Parse HTML once and cache list items with their text
            soup = BeautifulSoup(html, "html.parser")
            list_items: list[tuple[Tag, str]] = []
            for li in soup.find_all("li"):
                li_text = li.get_text(" ", strip=True)
                if li_text:  # Only cache non-empty items
                    list_items.append((li, li_text))

            # Process markdown lines
            fixed_lines: list[str] = []
            for line in lines:
                stripped = line.strip()

                # Skip table rows (they use | separators)
                if "|" in stripped and stripped.count("|") >= 2:
                    fixed_lines.append(line)
                    continue

                # Pattern: List item starting with verb, no link at start
                if (stripped.startswith("- ") or stripped.startswith("* ")) and stripped.lower().startswith(
                    ("- is ", "* is ", "- are ", "* are ", "- endpoints ", "* endpoints ")
                ):
                    # Try to find the missing link in HTML
                    item_text = stripped[2:].strip()
                    # Normalize for matching: remove markdown links [text](url) -> text, lowercase, single spaces
                    # Remove markdown links but keep the text
                    item_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item_text)
                    item_normalized = " ".join(item_clean.lower().split())
                    # Strip trailing punctuation for more flexible matching
                    item_key = item_normalized.rstrip(".,;:!? ")

                    # Look for matching list items (use cached text for faster matching)
                    matched = False
                    for li, li_text in list_items:
                        # Normalize HTML text for matching
                        li_normalized = " ".join(li_text.lower().split())
                        # Strip trailing punctuation from HTML too
                        li_normalized_clean = li_normalized.rstrip(".,;:!? ")
                        
                        # Check if markdown text appears in HTML text (HTML may have link text before it)
                        # Use a meaningful substring (first 40 chars) for matching to avoid punctuation issues
                        if len(item_key) > 40:
                            item_match = item_key[:40]
                        else:
                            item_match = item_key
                        
                        if item_match in li_normalized_clean:
                            # Only do DOM operations if text matches
                            strong_link = _find_strong_link_at_start(li)
                            if strong_link:
                                link_text, link_url = strong_link
                                # Inject the missing link
                                fixed_line = f"{stripped[:2]}**The [{link_text}]({link_url})** {item_text}"
                                fixed_lines.append(fixed_line)
                                matched = True
                                break

                    if not matched:
                        # No match found, keep original
                        fixed_lines.append(line)
                else:
                    fixed_lines.append(line)

            return "\n".join(fixed_lines)
        except Exception:
            # If anything fails, return original markdown
            return markdown


def _find_strong_link_at_start(li_tag: Tag) -> tuple[str, str] | None:
    """
    Find a nested strong+link structure at the start of a list item.

    Args:
        li_tag: BeautifulSoup list item tag

    Returns:
        Tuple of (link_text, link_url) if found, None otherwise
    """
    # Look for strong tag containing a link at the start
    for strong in li_tag.find_all("strong", recursive=False):
        link = strong.find("a", recursive=False)
        if link:
            link_text = link.get_text(strip=True)
            link_url = link.get("href", "")
            if link_text and link_url:
                return (link_text, link_url)

    # Also check if first child is strong with link
    first_child = next(iter(li_tag.children), None)
    if isinstance(first_child, Tag) and first_child.name == "strong":
        link = first_child.find("a")
        if link:
            link_text = link.get_text(strip=True)
            link_url = link.get("href", "")
            if link_text and link_url:
                return (link_text, link_url)

    return None


# Auto-register this fix
_fix_instance = MissingLinkTextFix()
register_fix(_fix_instance)
