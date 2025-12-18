"""Metrics calculation for parity comparison."""

from __future__ import annotations

import logging
import re
from typing import Any

LOGGER = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count (rough approximation: ~4 chars per token).

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return len(text) // 4


def count_links(markdown: str) -> tuple[int, int]:
    """
    Count total links and links missing anchor text.

    Args:
        markdown: Markdown content.

    Returns:
        Tuple of (total_links, links_missing_text).
    """
    # Match markdown links: [text](url) or [](url) or [text]()
    link_pattern = r'\[([^\]]*)\]\(([^)]+)\)'
    matches = re.findall(link_pattern, markdown)

    total_links = len(matches)
    links_missing_text = sum(1 for text, url in matches if not text.strip())

    return total_links, links_missing_text


def count_headings_by_level(markdown: str) -> dict[str, int]:
    """
    Count headings by level (h1-h6).

    Args:
        markdown: Markdown content.

    Returns:
        Dictionary with h1, h2, h3, h4, h5, h6 counts.
    """
    lines = markdown.splitlines()
    counts = {"h1": 0, "h2": 0, "h3": 0, "h4": 0, "h5": 0, "h6": 0}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # Count leading # characters
            level = 0
            for char in stripped:
                if char == "#":
                    level += 1
                else:
                    break
            if 1 <= level <= 6:
                counts[f"h{level}"] += 1

    return counts


def count_code_blocks(markdown: str) -> tuple[int, int]:
    """
    Count fenced code blocks and inline code.

    Args:
        markdown: Markdown content.

    Returns:
        Tuple of (fenced_blocks, inline_code).
    """
    # Fenced code blocks: ```...```
    fenced_pattern = r'```[^`]*```'
    fenced_blocks = len(re.findall(fenced_pattern, markdown, re.DOTALL))

    # Inline code: `code` (not part of fenced blocks)
    # Simple heuristic: count backticks that aren't part of triple backticks
    inline_code = markdown.count("`") - (fenced_blocks * 6)  # Rough estimate

    return fenced_blocks, max(0, inline_code)


def count_tables(markdown: str) -> int:
    """
    Count markdown tables.

    Args:
        markdown: Markdown content.

    Returns:
        Number of tables found.
    """
    lines = markdown.splitlines()
    table_count = 0
    in_table = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Table row: contains | characters
        if "|" in stripped and not stripped.startswith("```"):
            if not in_table:
                # Check if next line is separator (contains ---)
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if "|" in next_line and re.search(r'[-:]+', next_line):
                        in_table = True
                        table_count += 1
            # Check if table ends (empty line or non-table line)
            if in_table and (not stripped or "|" not in stripped):
                in_table = False
        elif in_table and not stripped:
            in_table = False

    return table_count


def cosine_similarity(text1: str, text2: str) -> float:
    """
    Calculate simple cosine similarity between two texts.

    Uses word frequency vectors (case-insensitive).

    Args:
        text1: First text.
        text2: Second text.

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    # Simple word-based similarity
    words1 = set(re.findall(r'\b\w+\b', text1.lower()))
    words2 = set(re.findall(r'\b\w+\b', text2.lower()))

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    if union == 0:
        return 0.0

    return intersection / union


def calculate_artefact_metrics(markdown: str) -> dict[str, Any]:
    """
    Calculate all metrics for a markdown artefact.

    Args:
        markdown: Markdown content to analyze.

    Returns:
        Dictionary with all calculated metrics.
    """
    char_count = len(markdown)
    word_count = len(markdown.split())
    token_count = estimate_tokens(markdown)

    total_links, links_missing_text = count_links(markdown)
    heading_counts = count_headings_by_level(markdown)
    fenced_blocks, inline_code = count_code_blocks(markdown)
    table_count = count_tables(markdown)

    return {
        "char_count": char_count,
        "word_count": word_count,
        "token_count": token_count,
        "link_count": total_links,
        "links_missing_text": links_missing_text,
        "heading_counts": heading_counts,
        "heading_total": sum(heading_counts.values()),
        "code_blocks_fenced": fenced_blocks,
        "code_blocks_inline": inline_code,
        "table_count": table_count,
    }


def calculate_similarity_metrics(
    firecrawl_markdown: str, baseline_markdown: str, enhanced_markdown: str
) -> dict[str, Any]:
    """
    Calculate similarity metrics between artefacts.

    Args:
        firecrawl_markdown: Firecrawl output.
        baseline_markdown: Baseline-static output.
        enhanced_markdown: Enhanced output.

    Returns:
        Dictionary with similarity scores.
    """
    return {
        "firecrawl_vs_baseline": cosine_similarity(firecrawl_markdown, baseline_markdown),
        "firecrawl_vs_enhanced": cosine_similarity(firecrawl_markdown, enhanced_markdown),
        "baseline_vs_enhanced": cosine_similarity(baseline_markdown, enhanced_markdown),
    }

