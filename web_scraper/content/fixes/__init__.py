"""Markdown fix plugins system.

This module provides a plugin-based system for fixing markdown quality issues
that arise from upstream tools (like Crawl4AI) missing certain patterns.

Each fix is a separate plugin that can be enabled/disabled independently.
This allows fixes to be turned off when upstream tools are updated.

Fixes are automatically registered when their modules are imported.
"""

from __future__ import annotations

# Import fixes to register them
from web_scraper.content.fixes import missing_link_text  # noqa: F401

from web_scraper.content.fixes.registry import apply_fixes, get_fix_registry

__all__ = ["apply_fixes", "get_fix_registry"]
