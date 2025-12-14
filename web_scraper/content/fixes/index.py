"""Index of all markdown fix plugins.

This module provides a human-readable index of all fixes, their purposes,
and how to enable/disable them. Use this for periodic review of whether
fixes are still needed as upstream tools are updated.
"""

from __future__ import annotations

from typing import Any

from web_scraper.content.fixes.registry import get_fix_registry


def get_fix_index() -> list[dict[str, Any]]:
    """
    Get an index of all registered fixes with metadata.

    Returns:
        List of dictionaries with fix metadata
    """
    fixes = get_fix_registry()
    return [
        {
            "name": fix.name,
            "description": fix.description,
            "issue_pattern": fix.issue_pattern,
            "upstream_issue": fix.upstream_issue,
            "enabled": fix.enabled,
        }
        for fix in fixes
    ]


def print_fix_index() -> None:
    """Print a human-readable index of all fixes."""
    index = get_fix_index()
    if not index:
        print("No markdown fixes registered.")
        return

    print("Markdown Fix Plugins Index")
    print("=" * 80)
    print()

    for i, fix in enumerate(index, 1):
        print(f"{i}. {fix['name']}")
        print(f"   Description: {fix['description']}")
        print(f"   Issue Pattern: {fix['issue_pattern']}")
        print(f"   Upstream Issue: {fix['upstream_issue']}")
        print()


if __name__ == "__main__":
    # Import fixes to register them
    from web_scraper.content.fixes import missing_link_text  # noqa: F401

    print_fix_index()
