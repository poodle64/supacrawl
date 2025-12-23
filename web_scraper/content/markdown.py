"""Markdown sanitisation utilities.

This module provides sanitize_markdown() for cleaning markdown content by
removing navigation blocks and link-heavy boilerplate.
"""

from __future__ import annotations

import re

from web_scraper.content.config import ExtractionConfig, get_config

# Markers that indicate navigation/boilerplate blocks
NAV_MARKERS = (
    "on this page",
    "table of contents",
    "related articles",
    "share this",
)


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

        # Preserve table blocks (they may have high link density but are content)
        if _is_table_block(stripped_block):
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


def _is_table_block(block: str) -> bool:
    """
    Check if block is a markdown table.

    Tables should be preserved even if they have high link density,
    since API documentation often has parameter tables with many links.

    Args:
        block: Text block to check.

    Returns:
        True if block appears to be a markdown table.
    """
    lines = block.strip().splitlines()
    if len(lines) < 2:
        return False

    # Check for table structure: | col | col | and separator row |---|---|
    pipe_lines = sum(1 for line in lines if line.strip().startswith("|"))
    separator_lines = sum(
        1 for line in lines if re.match(r"^\|[\s\-:|]+\|$", line.strip())
    )

    # A table needs at least 2 pipe-delimited lines and 1 separator
    return pipe_lines >= 2 and separator_lines >= 1


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
