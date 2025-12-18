"""Tests for readability extraction and canonical handling."""

from __future__ import annotations

from web_scraper.content import (
    extract_main_content_html,
    normalise_url,
    sanitize_markdown,
)


def test_normalise_url_prefers_canonical_and_strips_tracking() -> None:
    """Canonical link should override raw URL and drop tracking params."""
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://example.com/path?utm_source=news&ref=nav" />
      </head>
      <body></body>
    </html>
    """
    assert (
        normalise_url("https://example.com/path?utm_source=a#frag", html)
        == "https://example.com/path"
    )


def test_extract_main_content_html_prefers_article_over_nav() -> None:
    """Readability scorer should keep article body and drop nav noise."""
    html = """
    <html>
      <body>
        <nav><a href="/">Home</a> <a href="/docs">Docs</a></nav>
        <article><h1>Title</h1><p>Body text</p></article>
      </body>
    </html>
    """
    main = extract_main_content_html(html)
    assert "Body text" in main
    assert "Home" not in main


def test_sanitize_markdown_drops_link_heavy_nav_block() -> None:
    """Sanitizer should remove link-heavy navigation lists."""
    markdown = """
    # Overview

    On This Page

    - [Home](https://example.com)
    - [Docs](https://example.com/docs)
    - [Blog](https://example.com/blog)

    ## Content

    Body paragraph stays.
    """
    cleaned = sanitize_markdown(markdown)
    assert "On This Page" not in cleaned
    assert "Body paragraph stays." in cleaned
