"""Tests for markdown converter."""

from bs4 import BeautifulSoup

from supacrawl.services.converter import (
    SITE_PREPROCESSORS,
    MarkdownConverter,
    _detect_mkdocs_material,
    _preprocess_mkdocs_material,
    apply_site_preprocessors,
)


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

    def test_strips_javascript_links(self):
        """Test that javascript: links are removed entirely (UI controls)."""
        converter = MarkdownConverter()
        html = '<a href="javascript:window.print()">Print this page</a>'
        md = converter.convert(html, only_main_content=False)
        assert md.strip() == ""
        assert "Print this page" not in md
        assert "javascript:" not in md

    def test_strips_javascript_void_links(self):
        """Test that javascript:void(0) links are removed entirely."""
        converter = MarkdownConverter()
        html = '<a href="javascript:void(0)">Click me</a>'
        md = converter.convert(html, only_main_content=False)
        assert md.strip() == ""
        assert "Click me" not in md

    def test_preserves_non_javascript_protocols(self):
        """Test that other protocols like mailto: are preserved."""
        converter = MarkdownConverter()
        html = '<a href="mailto:test@example.com">Email</a>'
        md = converter.convert(html, only_main_content=False)
        assert "[Email](mailto:test@example.com)" in md

    def test_strips_javascript_case_insensitive(self):
        """Test that javascript: links are removed regardless of case."""
        converter = MarkdownConverter()
        # Uppercase
        html1 = '<a href="JAVASCRIPT:alert(1)">Uppercase</a>'
        md1 = converter.convert(html1, only_main_content=False)
        assert md1.strip() == ""
        assert "Uppercase" not in md1

        # Mixed case
        html2 = '<a href="JavaScript:void(0)">Mixed</a>'
        md2 = converter.convert(html2, only_main_content=False)
        assert md2.strip() == ""
        assert "Mixed" not in md2

    def test_strips_javascript_with_whitespace(self):
        """Test that javascript: links with leading/trailing whitespace are removed."""
        converter = MarkdownConverter()
        html = '<a href=" javascript:void(0) ">Whitespace</a>'
        md = converter.convert(html, only_main_content=False)
        assert md.strip() == ""
        assert "Whitespace" not in md

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
    """Tests for include_tags and exclude_tags filtering."""

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


class TestMkDocsMaterialPreprocessing:
    """Tests for MkDocs Material HTML preprocessing."""

    def test_strips_headerlink_anchors(self):
        """Test that permalink anchors are stripped from headings."""
        html = """
        <h1 id="title">Title<a class="headerlink" href="#title" title="Permanent link">¶</a></h1>
        <h2 id="section">Section<a class="headerlink" href="#section">¶</a></h2>
        """
        soup = BeautifulSoup(html, "html.parser")
        _preprocess_mkdocs_material(soup)

        # Headerlinks should be removed
        assert soup.select("a.headerlink") == []
        # But headings should remain
        assert soup.find("h1").get_text(strip=True) == "Title"
        assert soup.find("h2").get_text(strip=True) == "Section"

    def test_converts_highlighttable_to_code_block(self):
        """Test that line-numbered code tables are converted to proper code blocks."""
        html = """
        <table class="highlighttable">
            <tbody>
                <tr>
                    <td class="linenos">
                        <div class="linenodiv"><pre>1\n2</pre></div>
                    </td>
                    <td class="code">
                        <pre><code>int x = 1;
int y = 2;</code></pre>
                    </td>
                </tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        _preprocess_mkdocs_material(soup)

        # Table should be replaced with pre/code
        assert soup.find("table", class_="highlighttable") is None
        code = soup.find("code")
        assert code is not None
        assert "int x = 1" in code.get_text()
        assert "int y = 2" in code.get_text()

    def test_converts_admonition_to_blockquote(self):
        """Test that admonitions are converted to blockquotes with bold titles."""
        html = """
        <div class="admonition note">
            <p class="admonition-title">Note</p>
            <p>This is important information.</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        _preprocess_mkdocs_material(soup)

        # Admonition should be replaced with blockquote
        assert soup.find("div", class_="admonition") is None
        blockquote = soup.find("blockquote")
        assert blockquote is not None
        strong = blockquote.find("strong")
        assert strong is not None
        assert "Note:" in strong.get_text()
        assert "important information" in blockquote.get_text()

    def test_converts_admonition_with_custom_title(self):
        """Test that admonitions preserve custom titles."""
        html = """
        <div class="admonition example">
            <p class="admonition-title">Working with JSON</p>
            <p>Example content here.</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        _preprocess_mkdocs_material(soup)

        blockquote = soup.find("blockquote")
        assert blockquote is not None
        assert "Working with JSON:" in blockquote.get_text()
        assert "Example content" in blockquote.get_text()

    def test_handles_tabbed_content(self):
        """Test that tabbed content gets clear language headers."""
        html = """
        <div class="tabbed-set tabbed-alternate">
            <div class="tabbed-labels">
                <label>C#</label>
                <label>Python</label>
            </div>
            <div class="tabbed-content">
                <div class="tabbed-block">
                    <p>C# code example</p>
                </div>
                <div class="tabbed-block">
                    <p>Python code example</p>
                </div>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        _preprocess_mkdocs_material(soup)

        # Tabbed set should be replaced
        assert soup.find("div", class_="tabbed-set") is None
        # Should have h4 headers for each tab
        headers = soup.find_all("h4")
        assert len(headers) == 2
        header_texts = [h.get_text(strip=True) for h in headers]
        assert "C#" in header_texts
        assert "Python" in header_texts
        # Content should be preserved
        assert "C# code example" in soup.get_text()
        assert "Python code example" in soup.get_text()

    def test_full_conversion_with_mkdocs_material(self):
        """Test full conversion of MkDocs Material HTML to markdown."""
        converter = MarkdownConverter()
        html = """
        <html>
        <body>
            <article>
                <h1 id="title">Title<a class="headerlink" href="#title">¶</a></h1>
                <div class="admonition note">
                    <p class="admonition-title">Note</p>
                    <p>Important info.</p>
                </div>
                <table class="highlighttable">
                    <tr>
                        <td class="linenos"><pre>1</pre></td>
                        <td class="code"><pre><code>print("hello")</code></pre></td>
                    </tr>
                </table>
            </article>
        </body>
        </html>
        """
        md = converter.convert(html, only_main_content=False)

        # Heading should not have permalink
        assert "¶" not in md
        assert "headerlink" not in md
        # Should have Note blockquote
        assert "**Note:**" in md
        assert "Important info" in md
        # Code should be preserved
        assert 'print("hello")' in md
        # Should not have table markup for code
        assert "| ---" not in md

    def test_preserves_regular_tables(self):
        """Test that regular tables are not affected by highlighttable processing."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr><td>Data</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        _preprocess_mkdocs_material(soup)

        # Regular table should still exist
        assert soup.find("table") is not None
        assert "Header" in soup.get_text()
        assert "Data" in soup.get_text()

    def test_handles_empty_elements_gracefully(self):
        """Test that empty or malformed elements don't crash preprocessing."""
        html = """
        <div class="admonition note"></div>
        <table class="highlighttable"></table>
        <div class="tabbed-set"></div>
        """
        soup = BeautifulSoup(html, "html.parser")
        # Should not raise
        _preprocess_mkdocs_material(soup)


class TestSitePreprocessorRegistry:
    """Tests for the site preprocessor registry and detection."""

    def test_registry_has_mkdocs_material(self):
        """Test that MkDocs Material is registered."""
        names = [p.name for p in SITE_PREPROCESSORS]
        assert "mkdocs_material" in names

    def test_detect_mkdocs_by_md_content_class(self):
        """Test detection via md-content class."""
        html = '<div class="md-content"><p>Content</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _detect_mkdocs_material(soup) is True

    def test_detect_mkdocs_by_data_md_attribute(self):
        """Test detection via data-md-* attributes."""
        html = '<div data-md-component="content"><p>Content</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _detect_mkdocs_material(soup) is True

    def test_detect_mkdocs_by_multiple_indicators(self):
        """Test detection via combination of MkDocs elements."""
        html = """
        <h1>Title<a class="headerlink" href="#">¶</a></h1>
        <div class="admonition note"><p>Note</p></div>
        """
        soup = BeautifulSoup(html, "html.parser")
        assert _detect_mkdocs_material(soup) is True

    def test_no_detection_for_plain_html(self):
        """Test that plain HTML is not detected as MkDocs."""
        html = "<html><body><h1>Title</h1><p>Content</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        assert _detect_mkdocs_material(soup) is False

    def test_no_detection_for_single_indicator(self):
        """Test that a single indicator is not enough for detection."""
        html = '<h1>Title<a class="headerlink" href="#">¶</a></h1>'
        soup = BeautifulSoup(html, "html.parser")
        # Only one indicator (headerlink) - should not detect
        assert _detect_mkdocs_material(soup) is False

    def test_apply_site_preprocessors_returns_applied_names(self):
        """Test that apply_site_preprocessors returns list of applied preprocessors."""
        html = """
        <div class="md-content">
            <h1>Title<a class="headerlink" href="#">¶</a></h1>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        applied = apply_site_preprocessors(soup)
        assert "mkdocs_material" in applied

    def test_apply_site_preprocessors_empty_for_plain_html(self):
        """Test that no preprocessors are applied to plain HTML."""
        html = "<html><body><p>Plain content</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        applied = apply_site_preprocessors(soup)
        assert applied == []

    def test_preprocessor_registry_has_required_fields(self):
        """Test that all registered preprocessors have required documentation."""
        for preprocessor in SITE_PREPROCESSORS:
            assert preprocessor.name, "Preprocessor must have a name"
            assert preprocessor.description, "Preprocessor must have a description"
            assert preprocessor.examples, "Preprocessor must have example sites"
            assert callable(preprocessor.detect), "Preprocessor must have detect function"
            assert callable(preprocessor.preprocess), "Preprocessor must have preprocess function"
