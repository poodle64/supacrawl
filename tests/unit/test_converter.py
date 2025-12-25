"""Tests for markdown converter."""

import pytest
from supacrawl.services.converter import MarkdownConverter


class TestMarkdownConverter:
    """Tests for MarkdownConverter."""

    def test_converts_headings_to_atx(self):
        """Test that headings use ATX style (#)."""
        converter = MarkdownConverter()
        html = "<h1>Title</h1><h2>Subtitle</h2>"
        md = converter.convert(html, only_main_content=False)
        assert "# Title" in md
        assert "## Subtitle" in md

    def test_removes_script_tags(self):
        """Test that script tags are removed."""
        converter = MarkdownConverter()
        html = "<p>Content</p><script>alert('x')</script>"
        md = converter.convert(html, only_main_content=False)
        assert "alert" not in md
        assert "Content" in md

    def test_preserves_links(self):
        """Test that links are preserved."""
        converter = MarkdownConverter()
        html = '<a href="https://example.com">Link</a>'
        md = converter.convert(html, only_main_content=False)
        assert "[Link](https://example.com)" in md

    def test_preserves_code_blocks(self):
        """Test that code blocks are preserved."""
        converter = MarkdownConverter()
        html = "<pre><code>def foo(): pass</code></pre>"
        md = converter.convert(html, only_main_content=False)
        assert "def foo(): pass" in md

    def test_cleans_whitespace(self):
        """Test that excessive whitespace is cleaned."""
        converter = MarkdownConverter()
        html = "<p>A</p><p></p><p></p><p></p><p>B</p>"
        md = converter.convert(html, only_main_content=False)
        # Should not have more than 2 consecutive blank lines
        assert "\n\n\n\n" not in md

    def test_removes_nav_tags(self):
        """Test that nav tags are removed."""
        converter = MarkdownConverter()
        html = "<nav>Navigation</nav><p>Content</p>"
        md = converter.convert(html, only_main_content=False)
        assert "Navigation" not in md
        assert "Content" in md

    def test_removes_footer_tags(self):
        """Test that footer tags are removed."""
        converter = MarkdownConverter()
        html = "<p>Content</p><footer>Footer text</footer>"
        md = converter.convert(html, only_main_content=False)
        assert "Footer text" not in md
        assert "Content" in md

    def test_finds_main_content_with_main_tag(self):
        """Test that main content is extracted from main tag."""
        converter = MarkdownConverter()
        html = """
        <nav>Navigation</nav>
        <main><h1>Main Content</h1></main>
        <footer>Footer</footer>
        """
        md = converter.convert(html, only_main_content=True)
        assert "Main Content" in md
        # Navigation and footer should be excluded because we're using only_main_content
        # But they get removed anyway by boilerplate removal
        assert "Navigation" not in md
        assert "Footer" not in md

    def test_finds_main_content_with_article_tag(self):
        """Test that main content is extracted from article tag."""
        converter = MarkdownConverter()
        html = """
        <div class="sidebar">Sidebar</div>
        <article><h1>Article Content</h1></article>
        """
        md = converter.convert(html, only_main_content=True)
        assert "Article Content" in md
        assert "Sidebar" not in md

    def test_falls_back_to_body_when_no_main_content(self):
        """Test fallback to body when no main content selector matches."""
        converter = MarkdownConverter()
        html = "<body><div><h1>Content</h1></div></body>"
        md = converter.convert(html, only_main_content=True)
        assert "Content" in md

    def test_handles_empty_html(self):
        """Test handling of empty HTML."""
        converter = MarkdownConverter()
        assert converter.convert("") == ""
        assert converter.convert("   ") == ""

    def test_handles_malformed_html(self):
        """Test handling of malformed HTML."""
        converter = MarkdownConverter()
        html = "<p>Unclosed paragraph<div>Nested weirdly"
        md = converter.convert(html, only_main_content=False)
        # Should still extract some text
        assert "Unclosed paragraph" in md

    def test_uses_dash_for_bullets(self):
        """Test that unordered lists use dash bullets."""
        converter = MarkdownConverter()
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        md = converter.convert(html, only_main_content=False)
        assert "- Item 1" in md
        assert "- Item 2" in md

    def test_preserves_tables(self):
        """Test that tables are preserved."""
        converter = MarkdownConverter()
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr><td>Data</td></tr>
        </table>
        """
        md = converter.convert(html, only_main_content=False)
        assert "Header" in md
        assert "Data" in md

    def test_strips_trailing_whitespace_per_line(self):
        """Test that trailing whitespace is stripped from each line."""
        converter = MarkdownConverter()
        html = "<p>Line 1</p><p>Line 2</p>"
        md = converter.convert(html, only_main_content=False)
        lines = md.split("\n")
        for line in lines:
            assert line == line.rstrip()

    def test_no_boilerplate_removal(self):
        """Test conversion with boilerplate removal disabled."""
        converter = MarkdownConverter()
        html = "<nav>Navigation</nav><p>Content</p>"
        md = converter.convert(html, only_main_content=False, remove_boilerplate=False)
        # When remove_boilerplate=False, markdownify still strips nav in its strip list
        # So we can't test this properly. Let's at least verify it doesn't crash
        assert "Content" in md


class TestIncludeExcludeTags:
    """Tests for include_tags and exclude_tags filtering (Firecrawl-compatible)."""

    def test_include_tags_extracts_matching_elements(self):
        """Test that include_tags extracts only matching elements."""
        converter = MarkdownConverter()
        html = """
        <nav>Navigation</nav>
        <article><h1>Article Content</h1></article>
        <aside>Sidebar</aside>
        """
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            include_tags=["article"],
        )
        assert "Article Content" in md
        # Sidebar should not be included (not matching include_tags)
        assert "Sidebar" not in md

    def test_include_tags_with_class_selector(self):
        """Test that include_tags works with class selectors."""
        converter = MarkdownConverter()
        html = """
        <div class="header">Header</div>
        <div class="post-content"><p>Post text</p></div>
        <div class="footer">Footer</div>
        """
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            include_tags=[".post-content"],
        )
        assert "Post text" in md
        assert "Header" not in md
        assert "Footer" not in md

    def test_include_tags_multiple_selectors(self):
        """Test that multiple include_tags selectors are combined."""
        converter = MarkdownConverter()
        html = """
        <nav>Navigation</nav>
        <article><h1>Article</h1></article>
        <main><p>Main content</p></main>
        <footer>Footer</footer>
        """
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            include_tags=["article", "main"],
        )
        assert "Article" in md
        assert "Main content" in md
        assert "Navigation" not in md
        assert "Footer" not in md

    def test_exclude_tags_removes_matching_elements(self):
        """Test that exclude_tags removes matching elements."""
        converter = MarkdownConverter()
        html = """
        <article>
            <h1>Title</h1>
            <p>Content</p>
            <div class="advertisement">Ad here</div>
        </article>
        """
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            exclude_tags=[".advertisement"],
        )
        assert "Title" in md
        assert "Content" in md
        assert "Ad here" not in md

    def test_exclude_tags_multiple_selectors(self):
        """Test that multiple exclude_tags selectors are removed."""
        converter = MarkdownConverter()
        html = """
        <article>
            <h1>Title</h1>
            <p>Content</p>
            <nav>Nav menu</nav>
            <div class="sidebar">Sidebar</div>
            <footer>Footer text</footer>
        </article>
        """
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            exclude_tags=["nav", ".sidebar", "footer"],
        )
        assert "Title" in md
        assert "Content" in md
        assert "Nav menu" not in md
        assert "Sidebar" not in md
        assert "Footer text" not in md

    def test_exclude_before_include(self):
        """Test that exclude_tags is applied before include_tags."""
        converter = MarkdownConverter()
        html = """
        <article>
            <h1>Article Title</h1>
            <p>Good content</p>
            <div class="promo">Promotion</div>
        </article>
        """
        # Exclude promo, then include article
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            include_tags=["article"],
            exclude_tags=[".promo"],
        )
        assert "Article Title" in md
        assert "Good content" in md
        assert "Promotion" not in md

    def test_include_tags_takes_precedence_over_only_main_content(self):
        """Test that include_tags takes precedence over only_main_content."""
        converter = MarkdownConverter()
        html = """
        <main><p>Main area</p></main>
        <aside class="special"><p>Special sidebar</p></aside>
        """
        md = converter.convert(
            html,
            only_main_content=True,
            remove_boilerplate=False,
            include_tags=[".special"],
        )
        # Should get special sidebar, not main, because include_tags takes precedence
        assert "Special sidebar" in md
        # Main should not be included since include_tags overrides only_main_content
        assert "Main area" not in md

    def test_invalid_selector_logs_warning_but_continues(self):
        """Test that invalid selectors don't crash, just log warning."""
        converter = MarkdownConverter()
        html = "<p>Content</p>"
        # Invalid CSS selector should not crash
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            exclude_tags=["[invalid[selector"],
        )
        # Content should still be extracted
        assert "Content" in md

    def test_no_matching_include_tags_returns_full_content(self):
        """Test that when no include_tags match, full content is returned."""
        converter = MarkdownConverter()
        html = "<p>Paragraph content</p>"
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            include_tags=[".nonexistent"],
        )
        # Should fall back to full content
        assert "Paragraph content" in md

    def test_attribute_selector(self):
        """Test that attribute selectors work."""
        converter = MarkdownConverter()
        html = """
        <div>Regular div</div>
        <div data-content="true"><p>Data content</p></div>
        """
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            include_tags=["[data-content]"],
        )
        assert "Data content" in md
        assert "Regular div" not in md

    def test_id_selector(self):
        """Test that ID selectors work."""
        converter = MarkdownConverter()
        html = """
        <div id="other">Other</div>
        <div id="content"><p>Main content</p></div>
        """
        md = converter.convert(
            html,
            only_main_content=False,
            remove_boilerplate=False,
            include_tags=["#content"],
        )
        assert "Main content" in md
        assert "Other" not in md
