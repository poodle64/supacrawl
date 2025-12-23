"""Markdown fix plugins for common markdown conversion issues.

This module provides a functional registry for markdown fixes that can be
applied to address issues in markdown extraction from HTML.

Fixes can be:
- Applied selectively via site configuration
- Tracked via correlation IDs for debugging
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, Tag

LOGGER = logging.getLogger(__name__)


@dataclass
class FixSpec:
    """Specification for a markdown fix.

    Attributes:
        name: Unique identifier for this fix.
        description: Human-readable description.
        upstream_issue: Description of the markdown conversion issue.
        apply_fn: Function that takes (markdown, html) and returns fixed markdown.
    """

    name: str
    description: str
    upstream_issue: str
    apply_fn: Callable[[str, str], str]


def _fix_missing_link_text(markdown: str, html: str) -> str:
    """Fix missing link text in nested <strong><a> structures.

    Markdown conversion sometimes misses link text in <strong><a>text</a></strong>,
    producing markdown like "* is where..." instead of "* **[Link](url)** is where...".

    Args:
        markdown: Markdown content to fix.
        html: HTML content to reference.

    Returns:
        Fixed markdown content.
    """
    try:
        # Quick check: only process if we have lines that might need fixing
        lines = markdown.splitlines()
        needs_fixing = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")) and stripped.lower().startswith(
                ("- is ", "* is ", "- are ", "* are ", "- endpoints ", "* endpoints ")
            ):
                needs_fixing = True
                break

        if not needs_fixing:
            return markdown

        # Limit HTML size to prevent performance issues
        if len(html) > 1_000_000:
            return markdown

        # Parse HTML once and cache list items with their text
        soup = BeautifulSoup(html, "html.parser")
        list_items: list[tuple[Tag, str]] = []
        for li in soup.find_all("li"):
            li_text = li.get_text(" ", strip=True)
            if li_text:
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
            if stripped.startswith(("- ", "* ")) and stripped.lower().startswith(
                ("- is ", "* is ", "- are ", "* are ", "- endpoints ", "* endpoints ")
            ):

                item_text = stripped[2:].strip()
                # Normalize for matching: remove markdown links [text](url) -> text
                item_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item_text)
                item_normalized = " ".join(item_clean.lower().split())
                # Strip trailing punctuation for more flexible matching
                item_key = item_normalized.rstrip(".,;:!? ")

                # Look for matching list items
                matched = False
                for li, li_text in list_items:
                    # Normalize HTML text for matching
                    li_normalized = " ".join(li_text.lower().split())
                    li_normalized_clean = li_normalized.rstrip(".,;:!? ")

                    # Use meaningful substring for matching
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
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)

        return "\n".join(fixed_lines)
    except Exception:
        # If anything fails, return original markdown
        return markdown


def _find_strong_link_at_start(li_tag: Tag) -> tuple[str, str] | None:
    """Find a nested strong+link structure at the start of a list item.

    Args:
        li_tag: BeautifulSoup list item tag.

    Returns:
        Tuple of (link_text, link_url) if found, None otherwise.
    """
    # Look for strong tag containing a link at the start
    for strong in li_tag.find_all("strong", recursive=False):
        link = strong.find("a", recursive=False)
        if link:
            link_text = link.get_text(strip=True)
            href_attr = link.get("href", "")
            link_url = str(href_attr) if href_attr else ""
            if link_text and link_url:
                return (link_text, link_url)

    # Also check if first child is strong with link
    first_child = next(iter(li_tag.children), None)
    if isinstance(first_child, Tag) and first_child.name == "strong":
        link = first_child.find("a")
        if link:
            link_text = link.get_text(strip=True)
            href_attr = link.get("href", "")
            link_url = str(href_attr) if href_attr else ""
            if link_text and link_url:
                return (link_text, link_url)

    return None


def _fix_table_link_preservation(markdown: str, html: str) -> str:
    """Restore links in table cells that were stripped during markdown conversion.

    Content filtering in markdown conversion sometimes strips links from table cells,
    leaving empty cells where links should be. This fix restores those links
    from the original HTML.

    Args:
        markdown: Markdown content with potentially missing table links.
        html: HTML content to extract links from.

    Returns:
        Fixed markdown content with table links restored.
    """
    try:
        # Quick check: only process if we have tables in markdown
        if "|" not in markdown or "---|---" not in markdown:
            return markdown

        # Limit HTML size to prevent performance issues
        if len(html) > 2_000_000:
            return markdown

        # Parse HTML to extract table structure with links
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return markdown

        # Extract table data from HTML (preserve links)
        html_tables: list[list[list[str]]] = []
        for table in tables:
            rows: list[list[str]] = []
            for tr in table.find_all("tr"):
                cells: list[str] = []
                for td in tr.find_all(["td", "th"]):
                    # Extract cell content preserving links
                    cell_content = _extract_table_cell_content(td)
                    cells.append(cell_content)
                if cells:
                    rows.append(cells)
            if rows:
                html_tables.append(rows)

        if not html_tables:
            return markdown

        # Process markdown tables
        lines = markdown.splitlines()
        fixed_lines: list[str] = []
        in_table = False
        table_idx = -1
        row_idx = 0

        for line in lines:
            stripped = line.strip()

            # Detect table start (line with multiple |)
            if "|" in stripped and stripped.count("|") >= 2:
                if not in_table:
                    in_table = True
                    table_idx += 1
                    row_idx = 0

                # Skip separator line (---|---|---)
                if re.match(r"^[\s\|:-]+$", stripped):
                    fixed_lines.append(line)
                    continue

                # Process table row
                if table_idx < len(html_tables):
                    html_table = html_tables[table_idx]
                    if row_idx < len(html_table):
                        html_row = html_table[row_idx]
                        fixed_line = _restore_table_row_links(stripped, html_row)
                        fixed_lines.append(fixed_line)
                        row_idx += 1
                    else:
                        fixed_lines.append(line)
                else:
                    fixed_lines.append(line)
            else:
                # Not a table line
                if in_table:
                    in_table = False
                fixed_lines.append(line)

        return "\n".join(fixed_lines)
    except Exception:
        # If anything fails, return original markdown
        return markdown


def _extract_table_cell_content(td: Tag) -> str:
    """Extract content from a table cell, preserving links.

    Args:
        td: BeautifulSoup table cell tag.

    Returns:
        Cell content as markdown (with links if present).
    """
    # Check for link
    link = td.find("a")
    if link:
        link_text = link.get_text(strip=True)
        href_attr = link.get("href", "")
        link_url = str(href_attr) if href_attr else ""
        if link_text and link_url:
            return f"[{link_text}]({link_url})"

    # No link, just return text
    return td.get_text(strip=True)


def _restore_table_row_links(md_row: str, html_cells: list[str]) -> str:
    """Restore links in a markdown table row from HTML cell data.

    Args:
        md_row: Markdown table row (e.g., "| cell1 | cell2 | cell3 |").
        html_cells: List of cell contents from HTML (with links preserved).

    Returns:
        Fixed markdown row with links restored.
    """
    # Split markdown row by |
    cells = [cell.strip() for cell in md_row.split("|")]
    # Remove empty first/last elements from split
    cells = [c for c in cells if c or c == ""]

    # Match cells count
    if len(cells) != len(html_cells):
        return md_row

    # Restore links in empty or link-less cells
    fixed_cells: list[str] = []
    for md_cell, html_cell in zip(cells, html_cells):
        # If markdown cell is empty but HTML has content with link
        if (not md_cell or not md_cell.strip()) and html_cell and "[" in html_cell:
            fixed_cells.append(html_cell)
        # If markdown cell has text but no link, and HTML has link with same text
        elif md_cell and "[" not in md_cell and "[" in html_cell:
            # Extract text from HTML link
            match = re.match(r"\[([^\]]+)\]", html_cell)
            if match and match.group(1).strip() == md_cell.strip():
                fixed_cells.append(html_cell)
            else:
                fixed_cells.append(md_cell)
        else:
            fixed_cells.append(md_cell)

    # Reconstruct row
    return "| " + " | ".join(fixed_cells) + " |"


# Registry of all fixes
FIXES: list[FixSpec] = [
    FixSpec(
        name="missing-link-text-in-lists",
        description="Injects missing link text in list items from <strong><a> structures",
        upstream_issue="Markdown extraction misses link text in nested formatting structures",
        apply_fn=_fix_missing_link_text,
    ),
    FixSpec(
        name="table-link-preservation",
        description="Restores links in table cells stripped during markdown conversion",
        upstream_issue="Content filtering strips links from table cells",
        apply_fn=_fix_table_link_preservation,
    ),
]


def apply_fixes(
    markdown: str,
    html: str,
    correlation_id: str | None = None,
    config: Any | None = None,
) -> str:
    """Apply enabled markdown fixes.

    Args:
        markdown: Markdown content to fix.
        html: HTML content to reference.
        correlation_id: Optional correlation ID for logging.
        config: Optional SiteConfig with markdown_fixes configuration.

    Returns:
        Fixed markdown content.
    """
    # Check global enable flag
    fixes_enabled = False
    fix_overrides: dict[str, bool] = {}

    if config and hasattr(config, "markdown_fixes"):
        fixes_config = config.markdown_fixes
        fixes_enabled = fixes_config.enabled
        fix_overrides = fixes_config.fixes

    if not fixes_enabled:
        if correlation_id:
            LOGGER.debug(f"[{correlation_id}] Markdown fixes disabled globally")
        return markdown

    result = markdown
    applied_fixes: list[str] = []

    for fix in FIXES:
        # Check per-fix override
        if fix.name in fix_overrides and not fix_overrides[fix.name]:
            if correlation_id:
                LOGGER.debug(f"[{correlation_id}] Fix '{fix.name}' disabled by config")
            continue

        try:
            original = result
            result = fix.apply_fn(result, html)
            if result != original:
                applied_fixes.append(fix.name)
                if correlation_id:
                    LOGGER.debug(
                        f"[{correlation_id}] Applied fix '{fix.name}': {fix.description}"
                    )
        except Exception as e:
            LOGGER.warning(f"Fix '{fix.name}' failed: {e}", exc_info=True)
            # Continue with other fixes even if one fails

    if applied_fixes and correlation_id:
        LOGGER.info(
            f"[{correlation_id}] Applied {len(applied_fixes)} markdown fix(es): "
            f"{', '.join(applied_fixes)}"
        )

    return result


def get_fix_index() -> list[dict[str, Any]]:
    """Get an index of all registered fixes with metadata.

    Returns:
        List of dictionaries with fix metadata.
    """
    return [
        {
            "name": fix.name,
            "description": fix.description,
            "upstream_issue": fix.upstream_issue,
        }
        for fix in FIXES
    ]
