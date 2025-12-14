"""Content statistics utilities."""

from __future__ import annotations

import re
from typing import Any


def content_stats(markdown: str) -> dict[str, Any]:
    """
    Return simple per-page stats for logging/diagnostics.

    Args:
        markdown: Markdown content to analyse.

    Returns:
        Dictionary with:
            - characters: Total character count
            - heading_count: Number of headings
            - link_density: Ratio of markdown links to words
    """
    lines = markdown.splitlines()
    heading_count = sum(1 for line in lines if line.lstrip().startswith("#"))
    stats = {
        "characters": len(markdown),
        "heading_count": heading_count,
        "link_density": _link_density(markdown),
    }
    return stats


def _link_density(text: str) -> float:
    """
    Calculate link density as ratio of markdown links to words.

    Args:
        text: Text to analyse.

    Returns:
        Link density ratio.
    """
    if not text:
        return 0.0
    link_like = len(re.findall(r"\[[^\]]+\]\([^)]+\)", text))
    word_count = max(len(text.split()), 1)
    return link_like / word_count

