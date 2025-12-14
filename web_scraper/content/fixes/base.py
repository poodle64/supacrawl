"""Base classes for markdown fix plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MarkdownFix(ABC):
    """
    Base class for markdown fix plugins.

    Each fix plugin should:
    1. Inherit from this class
    2. Implement `fix()` method
    3. Provide metadata (name, description, issue_pattern)
    4. Register itself in the registry

    Fixes are applied in registration order.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this fix (e.g., 'missing-link-text-in-lists')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this fix does."""
        pass

    @property
    @abstractmethod
    def issue_pattern(self) -> str:
        """Description of the issue pattern this fix addresses."""
        pass

    @property
    @abstractmethod
    def upstream_issue(self) -> str:
        """Description of the upstream issue (e.g., 'Crawl4AI misses link text in nested <strong><a> structures')."""
        pass

    @abstractmethod
    def fix(self, markdown: str, html: str) -> str:
        """
        Apply this fix to markdown content.

        Args:
            markdown: Markdown content that may need fixing
            html: HTML content to reference for fixes

        Returns:
            Fixed markdown (or original if no fix needed)
        """
        pass

    @property
    def enabled(self) -> bool:
        """
        Whether this fix is enabled.

        Can be overridden to check environment variables or config.
        Defaults to True.
        """
        return True
