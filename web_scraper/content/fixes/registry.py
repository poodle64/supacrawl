"""Registry for markdown fix plugins."""

from __future__ import annotations

import logging
from typing import Any

from web_scraper.content.fixes.base import MarkdownFix

LOGGER = logging.getLogger(__name__)

# Global registry of all fixes
_REGISTRY: list[MarkdownFix] = []


def register_fix(fix: MarkdownFix) -> None:
    """
    Register a markdown fix plugin.

    Args:
        fix: Fix plugin instance to register
    """
    if fix.name in [f.name for f in _REGISTRY]:
        LOGGER.warning(f"Fix '{fix.name}' is already registered, skipping")
        return
    _REGISTRY.append(fix)
    LOGGER.debug(f"Registered markdown fix: {fix.name}")


def get_fix_registry() -> list[MarkdownFix]:
    """
    Get all registered fixes.

    Returns:
        List of registered fix plugins
    """
    return _REGISTRY.copy()


def apply_fixes(
    markdown: str,
    html: str,
    correlation_id: str | None = None,
    config: Any | None = None,
) -> str:
    """
    Apply all enabled fixes to markdown content.

    Args:
        markdown: Markdown content to fix
        html: HTML content to reference
        correlation_id: Optional correlation ID for logging
        config: Optional SiteConfig with markdown_fixes configuration

    Returns:
        Fixed markdown content
    """
    # Check config - fixes are disabled by default
    fixes_enabled = False
    fix_overrides: dict[str, bool] = {}
    
    if config and hasattr(config, "markdown_fixes"):
        fixes_config = config.markdown_fixes
        fixes_enabled = fixes_config.enabled
        fix_overrides = fixes_config.fixes

    # Global disable switch - fixes disabled by default
    if not fixes_enabled:
        if correlation_id:
            LOGGER.debug(
                f"[{correlation_id}] All markdown fixes disabled "
                f"(config.enabled={fixes_enabled})"
            )
        return markdown

    result = markdown
    applied_fixes: list[str] = []

    for fix in _REGISTRY:
        # Check if fix is enabled: config override > global enabled
        fix_enabled: bool = fixes_enabled
        
        # Config override takes precedence
        if fix.name in fix_overrides:
            fix_enabled = fix_overrides[fix.name]

        if not fix_enabled:
            if correlation_id:
                LOGGER.debug(f"[{correlation_id}] Fix '{fix.name}' is disabled, skipping")
            continue

        try:
            original = result
            result = fix.fix(result, html)
            if result != original:
                applied_fixes.append(fix.name)
                if correlation_id:
                    LOGGER.debug(
                        f"[{correlation_id}] Applied fix '{fix.name}': {fix.description}"
                    )
        except Exception as e:
            LOGGER.warning(
                f"Fix '{fix.name}' failed: {e}",
                exc_info=True,
            )
            # Continue with other fixes even if one fails

    if applied_fixes and correlation_id:
        LOGGER.info(
            f"[{correlation_id}] Applied {len(applied_fixes)} markdown fix(es): "
            f"{', '.join(applied_fixes)}"
        )

    return result


def clear_registry() -> None:
    """Clear the fix registry (mainly for testing)."""
    _REGISTRY.clear()
