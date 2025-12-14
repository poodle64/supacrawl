"""Main content extraction using DOM scoring heuristics."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup, Tag

from web_scraper.content.config import ExtractionConfig, get_config

# Weights for different tag types (higher = more likely main content)
TAG_WEIGHTS = {
    "article": 5.0,
    "main": 5.0,
    "section": 2.0,
    "div": 1.0,
    "body": 1.5,
}

# Tags that typically contain navigation/boilerplate (negative scores)
NEGATIVE_TAGS = {
    "nav": -5.0,
    "footer": -4.0,
    "aside": -3.0,
    "header": -2.0,
}

# Hints in class/id/role attributes that suggest main content
POSITIVE_HINTS = (
    "content",
    "article",
    "main",
    "doc",
    "body",
    "post",
    "story",
)

# Hints in class/id/role attributes that suggest navigation/boilerplate
NEGATIVE_HINTS = (
    "nav",
    "menu",
    "breadcrumb",
    "cookie",
    "social",
    "footer",
    "comment",
    "promo",
    "banner",
    "subscribe",
    "share",
    "toc",
)


def extract_main_content_html(html: str) -> str:
    """
    Score DOM blocks to return the most article-like container (HTML only).

    Args:
        html: Raw HTML content.

    Returns:
        HTML string of the best content block.
    """
    content, _ = extract_main_content(html)
    return content


def extract_main_content(html: str) -> tuple[str, dict[str, Any]]:
    """
    Return main content HTML and selection metadata.

    Uses heuristic scoring based on tag types, text length,
    link density, and class/id/role hints.

    Args:
        html: Raw HTML content.

    Returns:
        Tuple of (content_html, metadata_dict).
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    candidates = soup.find_all(_is_block_tag)
    if not candidates:
        return str(soup), {
            "selected_tag": None,
            "text_length": len(soup.get_text(" ", strip=True)),
            "link_density": 0.0,
        }

    best = max(candidates, key=_score_node)
    text = best.get_text(" ", strip=True)
    link_text_len = sum(len(a.get_text(" ", strip=True)) for a in best.find_all("a"))
    density = link_text_len / max(len(text), 1)
    meta = {
        "selected_tag": best.name,
        "text_length": len(text),
        "link_density": density,
    }
    return str(best), meta


def _is_block_tag(tag: Tag) -> bool:
    """Check if tag is a block-level container candidate."""
    if not isinstance(tag, Tag):
        return False
    return tag.name in {"article", "main", "section", "div", "body"}


def _score_node(tag: Tag, config: ExtractionConfig | None = None) -> float:
    """
    Score a node using tag weight, text density, link density, and hints.

    Higher scores indicate more likely main content.

    Args:
        tag: BeautifulSoup Tag to score.
        config: Extraction configuration. Uses default if not provided.

    Returns:
        Numeric score (higher = better).
    """
    if not isinstance(tag, Tag):
        return 0.0

    cfg = config or get_config()

    text = tag.get_text(" ", strip=True)
    text_len = len(text)
    if not text_len:
        return -10.0

    link_text_len = sum(len(a.get_text(" ", strip=True)) for a in tag.find_all("a"))
    link_density = link_text_len / max(text_len, 1)

    score = TAG_WEIGHTS.get(tag.name, 0.5)
    score += min(text_len / cfg.text_length_score_divisor, cfg.max_text_length_score)
    score -= link_density * 5

    # Build attribute string for hint matching
    tag_id = tag.get("id") or ""
    tag_class_attr: list[str] | str = tag.get("class") or []
    tag_role = tag.get("role") or ""
    # Handle cases where attributes might be lists or strings
    id_str: str = (
        tag_id if isinstance(tag_id, str) else " ".join(tag_id) if tag_id else ""
    )
    class_str: str = (
        " ".join(tag_class_attr)
        if isinstance(tag_class_attr, list)
        else str(tag_class_attr) if tag_class_attr else ""
    )
    role_str: str = (
        tag_role if isinstance(tag_role, str) else " ".join(tag_role) if tag_role else ""
    )
    attr_str = " ".join([id_str, class_str, role_str]).lower()
    if any(h in attr_str for h in POSITIVE_HINTS):
        score += 3
    if any(h in attr_str for h in NEGATIVE_HINTS):
        score -= 4

    if tag.name in NEGATIVE_TAGS:
        score += NEGATIVE_TAGS[tag.name]

    # Penalise very short blocks heavily linked
    if text_len < cfg.min_text_for_link_penalty and link_density > cfg.link_density_penalty_threshold:
        score -= 6

    return score

