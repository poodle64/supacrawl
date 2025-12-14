"""Content cleaning utilities using configurable patterns.

This module provides configurable content cleaning that replaces
hardcoded site-specific logic with pattern-based cleaning.
"""

from __future__ import annotations

import re

from web_scraper.models import CleaningConfig

# Common SDK/language tab patterns that get concatenated
TAB_PATTERNS = [
    (r"HTTPPHP SDK", "HTTP | PHP SDK"),
    (r"JavaScript SDKAndroid SDK", "JavaScript SDK | Android SDK"),
    (r"Android SDKiOS SDK", "Android SDK | iOS SDK"),
    (r"PHP SDKJavaScript SDK", "PHP SDK | JavaScript SDK"),
    (r"SDKJavaScript", "SDK | JavaScript"),
    (r"SDKAndroid", "SDK | Android"),
    (r"SDKiOS", "SDK | iOS"),
]


def clean_markdown(
    markdown: str,
    config: CleaningConfig | None = None,
) -> str:
    """
    Clean markdown content using configurable patterns.

    Applies the following cleaning steps:
    1. Skip to first heading (if configured)
    2. Filter lines matching tracker patterns
    3. Strip configured prefixes
    4. Stop at configured markers

    Args:
        markdown: Raw markdown content.
        config: Cleaning configuration. Uses defaults if not provided.

    Returns:
        Cleaned markdown string.
    """
    if config is None:
        config = CleaningConfig()

    lines = markdown.splitlines()
    cleaned: list[str] = []

    # Skip everything until first heading (if configured)
    started = not config.skip_until_heading
    for line in lines:
        text = line.strip()

        # Skip until first heading
        if not started:
            if (
                text.startswith("# ")
                or text.startswith("## ")
                or text.startswith("### ")
            ):
                started = True
            else:
                continue

        # Check for stop markers
        if any(marker in text for marker in config.stop_markers):
            break

        # Filter tracker patterns (in image/link lines)
        if text.startswith("![") and any(
            sub in text for sub in config.tracker_patterns
        ):
            continue

        # Skip lines matching strip prefixes
        if any(text.startswith(pref) for pref in config.strip_prefixes):
            continue

        # Skip navigation markers
        if any(marker.lower() in text.lower() for marker in config.nav_markers):
            continue

        # Skip link-only rows that look like navigation
        if text.startswith("[") and "](" in text:
            # If it's just a link with no other content, might be nav
            link_text = text.split("]")[0][1:] if "]" in text else ""
            if len(link_text.split()) <= 3:
                # Short link text, likely navigation
                continue

        cleaned.append(line)

    result = "\n".join(cleaned).strip()
    return result or markdown


def fix_common_markdown_issues(markdown: str) -> str:
    """
    Fix common markdown issues from Crawl4AI output.

    Handles:
    - Concatenated tab/button labels (e.g., "HTTPPHP SDKJavaScript SDK...")
    - Malformed table separators

    Args:
        markdown: Markdown content to fix.

    Returns:
        Fixed markdown string.
    """
    result = markdown

    # Fix concatenated SDK/language tabs
    for pattern, replacement in TAB_PATTERNS:
        result = result.replace(pattern, replacement)

    # Fix more complex concatenated patterns using regex
    # Pattern: word ending in lowercase followed by word starting with uppercase
    # that looks like SDK/language names
    sdk_names = r"(HTTP|PHP|SDK|JavaScript|Android|iOS|Python|Ruby|Java|C#|Go|Rust|Swift|Kotlin|cURL|curl)"
    result = re.sub(
        rf"({sdk_names})({sdk_names})",
        r"\1 | \2",
        result,
    )

    # Fix table rows that have misaligned pipes
    lines = result.splitlines()
    fixed_lines = []
    for line in lines:
        # If line looks like a table row but has formatting issues
        if line.count("|") >= 2:
            # Clean up extra whitespace around pipes
            line = re.sub(r"\s*\|\s*", " | ", line)
            line = line.strip()
            if line.startswith("| "):
                line = line[2:]
            if line.endswith(" |"):
                line = line[:-2]
        fixed_lines.append(line)

    return "\n".join(fixed_lines)


def apply_cleaning_config(
    markdown: str,
    config: CleaningConfig,
) -> str:
    """
    Apply full cleaning pipeline with configuration.

    This is the main entry point for configurable content cleaning.

    Args:
        markdown: Raw markdown content.
        config: Cleaning configuration from SiteConfig.

    Returns:
        Cleaned markdown string.
    """
    # First fix common Crawl4AI output issues
    markdown = fix_common_markdown_issues(markdown)
    # Then apply configured cleaning
    return clean_markdown(markdown, config)

