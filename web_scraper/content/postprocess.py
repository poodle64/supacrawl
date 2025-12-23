"""Markdown post-processing result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarkdownPostprocessResult:
    """Result of markdown post-processing pipeline.

    Attributes:
        markdown: Processed markdown content after sanitization.
        language: Deprecated, always empty dict. Kept for API compatibility.
    """

    markdown: str
    language: dict[str, Any] = field(default_factory=dict)
