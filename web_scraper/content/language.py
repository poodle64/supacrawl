"""Language detection and content filtering utilities."""

from __future__ import annotations

import re
from typing import Any

from web_scraper.content.config import ExtractionConfig, get_config

# Common English stopwords for language detection
ENGLISH_STOPWORDS = {
    "the",
    "and",
    "of",
    "to",
    "in",
    "for",
    "with",
    "on",
    "by",
    "is",
    "this",
    "that",
    "from",
    "as",
}


def detect_language(
    markdown: str, config: ExtractionConfig | None = None
) -> dict[str, Any]:
    """
    Lightweight language detection and optional paragraph filtering.

    Uses heuristic based on ratio of ASCII letters and common English stopwords.
    Optionally filters non-English paragraphs while preserving headings.

    Args:
        markdown: Markdown content to analyse.
        config: Extraction configuration. Uses default if not provided.

    Returns:
        Dictionary with:
            - language: Detected language code ("en", "mixed", "unknown")
            - confidence: Score from 0.0 to 1.0
            - action: What was done ("none", "filtered_paragraphs", "flagged_non_en")
            - content: Potentially filtered content
    """
    cfg = config or get_config()
    min_ratio = cfg.min_english_stopword_ratio

    paragraphs = [p.strip() for p in markdown.split("\n\n") if p.strip()]
    if not paragraphs:
        return {
            "language": "unknown",
            "confidence": 0.0,
            "action": "none",
            "content": markdown,
        }

    # Extract headings before filtering (they're important structure)
    heading_lines = [
        line
        for line in markdown.splitlines()
        if line.strip() and line.strip().startswith("#")
    ]

    def score(text: str) -> float:
        words = [w.lower() for w in re.findall(r"[a-zA-Z]+", text)]
        if not words:
            return 0.0
        stopword_hits = sum(1 for w in words if w in ENGLISH_STOPWORDS)
        return stopword_hits / len(words)

    scores = [score(p) for p in paragraphs]
    avg_score = sum(scores) / len(scores)
    language = "en" if avg_score >= min_ratio else "unknown"
    action = "none"
    filtered_content = markdown

    if language != "en":
        # Always preserve heading paragraphs (they're structure, not content)
        kept_paragraphs = [
            p
            for p, s in zip(paragraphs, scores)
            if s >= min_ratio or any(line.strip() in p for line in heading_lines)
        ]
        if kept_paragraphs:
            filtered_content = "\n\n".join(kept_paragraphs)
            language = "mixed"
            action = "filtered_paragraphs"
        else:
            action = "flagged_non_en"

    # Ensure headings are preserved in filtered content
    filtered_headings = [
        line
        for line in filtered_content.splitlines()
        if line.strip() and line.strip().startswith("#")
    ]
    if heading_lines and not filtered_headings:
        # Prepend headings if they were filtered out (use config limit)
        headings_to_add = heading_lines[: cfg.max_headings_to_restore]
        filtered_content = "\n".join(headings_to_add) + "\n\n" + filtered_content

    confidence = round(min(max(avg_score, 0.0), 1.0), 3)
    return {
        "language": language,
        "confidence": confidence,
        "action": action,
        "content": filtered_content,
    }

