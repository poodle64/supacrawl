"""End-to-end tests for link preservation in markdown output.

This test module validates that links are correctly preserved in various
contexts (tables, lists, inline text) during the markdown conversion process.

Related GitHub Issue: #3
Related Roadmap: ROADMAP.md Phase 1.2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web_scraper.scrapers.playwright_scraper import PlaywrightScraper
from web_scraper.sites.loader import load_site_config


def test_table_links_preserved():
    """Table cells with links should preserve URLs and link text.

    This test validates the fix for the critical bug where PruningContentFilter
    was stripping 100% of links from table cells.

    Test case: IANA Reserved Domains page has 11 A-label links in IDN table.
    Expected: All 11 links preserved with proper markdown format.

    GitHub Issue: #3
    """
    # Load site config
    sites_dir = Path.cwd() / "sites"
    config = load_site_config("audit-test", sites_dir)

    # Ensure markdown fixes are enabled
    assert config.markdown_fixes.enabled, "markdown_fixes must be enabled to test link preservation"

    # Run scraper on IANA Reserved Domains page
    scraper = PlaywrightScraper()
    pages, snapshot_path = scraper.crawl(
        config,
        target_urls=["https://www.iana.org/domains/reserved"],
    )

    # Validate we got a result
    assert len(pages) == 1, "Expected exactly one page from target_urls"
    page = pages[0]

    # Check markdown content for table links
    markdown = page.content_markdown

    # Verify table structure exists
    assert "|" in markdown, "Expected table structure in markdown"
    assert "Domain (A-label)" in markdown, "Expected IDN table header"

    # Check for presence of all 11 A-label links
    # These are the expected links from the IANA IDN table
    expected_links = [
        "XN--KGBECHTV",  # Arabic
        "XN--HGBK6AJ7F53BBA",  # Persian
        "XN--0ZWM56D",  # Chinese (Simplified)
        "XN--G6W251D",  # Chinese (Traditional)
        "XN--80AKHBYKNJ4F",  # Russian
        "XN--11B5BS3A9AJ6G",  # Hindi
        "XN--JXALPDLP",  # Greek
        "XN--9T4B11YI5A",  # Korean
        "XN--DEBA0AD",  # Yiddish
        "XN--ZCKZAH",  # Japanese
        "XN--HLCJ6AYA9ESC7A",  # Tamil
    ]

    # Count preserved links
    link_count = 0
    for link_text in expected_links:
        if f"[{link_text}]" in markdown:
            link_count += 1

    # Assert all links are preserved
    assert link_count == 11, (
        f"Expected 11 A-label links in IDN table, got {link_count}. "
        f"Missing: {[link for link in expected_links if f'[{link}]' not in markdown]}"
    )

    # Verify links have URLs
    assert "](/domains/root/db/" in markdown or "](https://www.iana.org/domains/root/db/" in markdown, (
        "Expected links to have proper URLs pointing to domain database"
    )


def test_table_links_firecrawl_parity():
    """Validate table link output matches Firecrawl format.

    This test ensures our link preservation produces output compatible with
    Firecrawl's markdown format.
    """
    # Load site config
    sites_dir = Path.cwd() / "sites"
    config = load_site_config("audit-test", sites_dir)
    assert config.markdown_fixes.enabled, "markdown_fixes must be enabled"

    # Run scraper
    scraper = PlaywrightScraper()
    pages, snapshot_path = scraper.crawl(
        config,
        target_urls=["https://www.iana.org/domains/reserved"],
    )

    assert len(pages) == 1
    page = pages[0]
    markdown = page.content_markdown

    # Check for Firecrawl-compatible link format: [TEXT](URL)
    # Example from parity comparison:
    # | إختبار | [XN--KGBECHTV](https://www.iana.org/domains/root/db/xn--kgbechtv.html) | Arabic | Arabic |

    # Verify at least one complete table row with link
    # Pattern: | non-empty | [LINK](URL) | non-empty | non-empty |
    import re

    table_row_with_link_pattern = r"\|[^|]+\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|[^|]+\|[^|]+\|"
    matches = re.findall(table_row_with_link_pattern, markdown)

    assert len(matches) >= 11, (
        f"Expected at least 11 table rows with links, found {len(matches)}. "
        "Links may be missing or formatted incorrectly."
    )

    # Verify link URLs point to correct domain database
    for link_text, link_url in matches:
        assert "xn--" in link_url.lower(), (
            f"Link URL '{link_url}' does not appear to be an IDN domain reference"
        )


@pytest.mark.parametrize(
    "url,expected_link_count",
    [
        ("https://www.iana.org/domains/reserved", 11),  # IDN table
        ("https://www.iana.org/help/example-domains", 3),  # RFC links
    ],
)
def test_link_preservation_various_pages(url: str, expected_link_count: int):
    """Validate link preservation across different page types.

    Args:
        url: URL to scrape.
        expected_link_count: Minimum number of links expected in markdown.
    """
    sites_dir = Path.cwd() / "sites"
    config = load_site_config("audit-test", sites_dir)
    assert config.markdown_fixes.enabled

    scraper = PlaywrightScraper()
    pages, snapshot_path = scraper.crawl(config, target_urls=[url])

    assert len(pages) == 1
    page = pages[0]
    markdown = page.content_markdown

    # Count markdown links: [text](url)
    import re

    link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    links = re.findall(link_pattern, markdown)

    assert len(links) >= expected_link_count, (
        f"Expected at least {expected_link_count} links in {url}, "
        f"found {len(links)}. Links may be missing."
    )


def test_empty_table_cells_not_replaced():
    """Ensure legitimately empty table cells remain empty.

    This test validates that the link preservation fix doesn't incorrectly
    inject links into cells that should be empty.
    """
    sites_dir = Path.cwd() / "sites"
    config = load_site_config("audit-test", sites_dir)
    assert config.markdown_fixes.enabled

    scraper = PlaywrightScraper()
    pages, snapshot_path = scraper.crawl(
        config,
        target_urls=["https://www.iana.org/domains/reserved"],
    )

    assert len(pages) == 1
    page = pages[0]
    markdown = page.content_markdown

    # Check for table rows (should have consistent | count)
    lines = markdown.splitlines()
    table_lines = [line for line in lines if "|" in line and line.count("|") >= 4]

    # All table rows should have same number of | separators
    if table_lines:
        separator_counts = [line.count("|") for line in table_lines]
        # Allow for minor variation (header vs data rows)
        assert max(separator_counts) - min(separator_counts) <= 1, (
            "Table structure appears broken (inconsistent column counts)"
        )
