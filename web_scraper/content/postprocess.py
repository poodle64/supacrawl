"""Markdown post-processing result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MarkdownPostprocessResult:
    """Result of markdown post-processing pipeline.

    Attributes:
        markdown: Processed markdown content after fixes, sanitization, and language filtering.
        language: Language detection information dictionary with keys:
            - language: Detected language code ("en", "mixed", "unknown")
            - confidence: Score from 0.0 to 1.0
            - action: What was done ("none", "filtered_paragraphs", "flagged_non_en")
            - content: Potentially filtered content (same as markdown after processing)
    """

    markdown: str
    language: dict[str, Any]
