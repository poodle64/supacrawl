"""HTML to markdown conversion and markdown sanitisation."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from web_scraper.content.config import ExtractionConfig, get_config

# Markers that indicate navigation/boilerplate blocks
NAV_MARKERS = (
    "on this page",
    "table of contents",
    "related articles",
    "share this",
)


def html_to_markdown(html: str) -> str:
    """
    Convert a subset of HTML to lightweight markdown.

    Handles: headings, paragraphs, lists, code blocks, and tables.

    Args:
        html: HTML content to convert.

    Returns:
        Markdown string.
    """
    soup = BeautifulSoup(html, "html.parser")
    root: Tag | BeautifulSoup = soup.body if soup.body else soup

    lines: list[str] = []

    def render(node: Any) -> None:
        if not isinstance(node, Tag):
            return
        name = node.name

        # Handle structural tags
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            heading_text = _extract_text_with_links(node)
            if heading_text:
                lines.append(f"{'#' * level} {heading_text}")
        elif name in {"p", "div", "section", "article"}:
            para_text = _extract_text_with_links(node)
            if para_text:
                lines.append(para_text)
        elif name in {"ul", "ol"}:
            list_items = node.find_all("li", recursive=False)
            for item in list_items:
                item_text = _extract_text_with_links(item)
                if item_text:
                    prefix = "- " if name == "ul" else "1. "
                    lines.append(f"{prefix}{item_text}")
        elif name == "li":
            # Handle nested lists
            item_text = _extract_text_with_links(node)
            if item_text:
                lines.append(f"- {item_text}")
        elif name == "table":
            table_lines = _table_to_markdown(node)
            lines.extend(table_lines)
        elif name in {"pre", "code"}:
            code_text = node.get_text()
            if code_text.strip():
                lines.append(f"```\n{code_text}\n```")
        elif name == "blockquote":
            quote_text = _extract_text_with_links(node)
            if quote_text:
                lines.append(f"> {quote_text}")

    for child in root.children:
        render(child)

    return "\n\n".join(lines).strip()


def _extract_text_with_links(node: Tag) -> str:
    """
    Extract text from a node, preserving links and formatting.

    Args:
        node: BeautifulSoup Tag node.

    Returns:
        Markdown-formatted text with links.
    """
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, Tag):
            if child.name == "a":
                href = child.get("href", "")
                link_text = child.get_text(" ", strip=True)
                if href and link_text:
                    # Check if parent is strong/bold - if so, wrap link in bold
                    parent = child.parent
                    if parent and parent.name in {"strong", "b"}:
                        parts.append(f"**[{link_text}]({href})**")
                    else:
                        parts.append(f"[{link_text}]({href})")
                elif link_text:
                    parts.append(link_text)
            elif child.name in {"strong", "b"}:
                # Extract text from strong tag, preserving any links inside
                strong_text = _extract_text_with_links(child)
                if strong_text:
                    # If it contains a link, the link already has bold formatting
                    if "[[" in strong_text or strong_text.startswith("[") and "]**" in strong_text:
                        parts.append(strong_text)
                    else:
                        parts.append(f"**{strong_text}**")
            elif child.name in {"em", "i"}:
                em_text = _extract_text_with_links(child)
                if em_text:
                    parts.append(f"*{em_text}*")
            else:
                # Recursively extract from other tags
                child_text = _extract_text_with_links(child)
                if child_text:
                    parts.append(child_text)
        else:
            # Text node - preserve whitespace
            text = str(child)
            # Only add non-empty text
            if text.strip():
                parts.append(text.strip())
    # Join parts with single space, but preserve structure
    return " ".join(parts).strip()


def _table_to_markdown(table: Tag) -> list[str]:
    """
    Convert a simple HTML table to markdown rows.

    Args:
        table: BeautifulSoup table Tag.

    Returns:
        List of markdown table lines.
    """
    table_rows: list[list[str]] = []
    for tr_elem in table.find_all("tr"):
        cells = tr_elem.find_all(["th", "td"])
        if not cells:
            continue
        table_rows.append([cell.get_text(" ", strip=True) for cell in cells])

    if not table_rows:
        return []

    output: list[str] = []
    header_row: list[str] = table_rows[0]
    output.append(" | ".join(header_row))
    output.append(" | ".join(["---"] * len(header_row)))
    for data_row in table_rows[1:]:
        output.append(" | ".join(data_row))
    return output


def sanitize_markdown(markdown: str, config: ExtractionConfig | None = None) -> str:
    """
    Trim markdown to main content window and drop link-heavy/nav blocks.

    Args:
        markdown: Markdown content to sanitise.
        config: Extraction configuration. Uses default if not provided.

    Returns:
        Cleaned markdown string.
    """
    cfg = config or get_config()
    lines = markdown.splitlines()

    # Keep content from first heading onwards
    started = False
    kept: list[str] = []
    for line in lines:
        if not started:
            if line.lstrip().startswith("#"):
                started = True
                kept.append(line)
            continue
        kept.append(line)

    blocks = "\n".join(kept).split("\n\n") if kept else markdown.split("\n\n")
    cleaned_blocks: list[str] = []
    for block in blocks:
        stripped_block = block.strip()
        # Always preserve heading-only blocks (they're important structure)
        is_heading_block = (
            stripped_block
            and stripped_block.startswith("#")
            and len(
                [
                    ln
                    for ln in stripped_block.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
            )
            == 0
        )
        if is_heading_block:
            cleaned_blocks.append(block.strip())
            continue

        # Also preserve blocks that start with headings (heading + some content)
        if stripped_block and any(
            line.strip().startswith("#")
            for line in stripped_block.splitlines()[:2]
        ):
            # Check if it's a nav block before preserving
            if not _is_nav_marker(block):
                cleaned_blocks.append(block.strip())
                continue

        density = _link_density(block)
        word_count = len(block.split())
        if word_count < cfg.min_block_word_count and density > cfg.nav_block_link_density:
            continue
        if _is_nav_marker(block):
            continue
        cleaned_blocks.append(block.strip())

    cleaned = "\n\n".join(_collapse_blank_lines([b for b in cleaned_blocks if b]))
    return cleaned.strip() or markdown


def _link_density(text: str) -> float:
    """
    Calculate link density as ratio of markdown links to words.

    Args:
        text: Text to analyse.

    Returns:
        Link density ratio (0.0 to 1.0+).
    """
    if not text:
        return 0.0
    link_like = len(re.findall(r"\[[^\]]+\]\([^)]+\)", text))
    word_count = max(len(text.split()), 1)
    return link_like / word_count


def _is_nav_marker(block: str) -> bool:
    """
    Check if block contains navigation/boilerplate markers.

    Args:
        block: Text block to check.

    Returns:
        True if block appears to be navigation.
    """
    lowered = block.lower()
    return any(marker in lowered for marker in NAV_MARKERS)


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    """
    Remove consecutive blank lines, keeping at most one.

    Args:
        lines: List of lines.

    Returns:
        Cleaned list of lines.
    """
    output: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        output.append(line)
        previous_blank = is_blank
    return output
