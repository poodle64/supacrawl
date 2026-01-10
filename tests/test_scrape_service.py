"""Tests for scrape service."""

import pytest

from supacrawl.models import ContentStats, ProcessMetadata, ScrapeResult
from supacrawl.services.scrape import (
    ScrapeService,
    _count_extracted_elements,
    _detect_content_issues,
    _generate_content_warnings,
)


@pytest.mark.e2e
class TestScrapeService:
    """Tests for ScrapeService (E2E - require browser/network)."""

    @pytest.mark.asyncio
    async def test_scrape_returns_markdown(self):
        """Test that scrape returns markdown content."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert isinstance(result, ScrapeResult)
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert len(result.data.markdown) > 0

    @pytest.mark.asyncio
    async def test_scrape_extracts_metadata(self):
        """Test that scrape extracts page metadata."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert result.success
        assert result.data is not None
        assert result.data.metadata is not None
        assert result.data.metadata.title is not None
        assert result.data.metadata.source_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_scrape_returns_html_when_requested(self):
        """Test that scrape returns HTML when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["html"])
        assert result.success
        assert result.data is not None
        assert result.data.html is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_raw_html_when_requested(self):
        """Test that scrape returns raw HTML when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["rawHtml"])
        assert result.success
        assert result.data is not None
        assert result.data.raw_html is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_links_when_requested(self):
        """Test that scrape returns links when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["links"])
        assert result.success
        assert result.data is not None
        assert result.data.links is not None
        assert isinstance(result.data.links, list)

    @pytest.mark.asyncio
    async def test_scrape_returns_multiple_formats(self):
        """Test that scrape can return multiple formats."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["markdown", "html", "links"])
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert result.data.html is not None
        assert result.data.links is not None

    @pytest.mark.asyncio
    async def test_scrape_handles_error(self):
        """Test that scrape handles errors gracefully."""
        service = ScrapeService()
        result = await service.scrape("https://invalid-url-that-does-not-exist.example")
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_json_with_prompt(self):
        """Test that scrape returns JSON data when json format requested with prompt."""
        service = ScrapeService()
        result = await service.scrape(
            "https://example.com",
            formats=["json"],
            json_prompt="Extract the page title and domain name",
        )
        assert result.success
        assert result.data is not None
        # JSON extraction may fail if Ollama is not running, but should not crash
        # We just check the structure is correct
        if result.data.llm_extraction is not None:
            assert isinstance(result.data.llm_extraction, dict)

    @pytest.mark.asyncio
    async def test_scrape_returns_json_with_schema(self):
        """Test that scrape returns JSON data when json format requested with schema."""
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "domain": {"type": "string"},
            },
            "required": ["title", "domain"],
        }
        service = ScrapeService()
        result = await service.scrape(
            "https://example.com",
            formats=["json"],
            json_schema=schema,
        )
        assert result.success
        assert result.data is not None
        # JSON extraction may fail if Ollama is not running, but should not crash
        # We just check the structure is correct
        if result.data.llm_extraction is not None:
            assert isinstance(result.data.llm_extraction, dict)

    @pytest.mark.asyncio
    async def test_scrape_returns_multiple_formats_including_json(self):
        """Test that scrape can return multiple formats including JSON."""
        service = ScrapeService()
        result = await service.scrape(
            "https://example.com",
            formats=["markdown", "json"],
            json_prompt="Extract page info",
        )
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        # JSON may be None if extraction fails, but shouldn't crash
        assert result.data.llm_extraction is None or isinstance(result.data.llm_extraction, dict)

    @pytest.mark.asyncio
    async def test_scrape_returns_images_when_requested(self):
        """Test that scrape returns images when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["images"])
        assert result.success
        assert result.data is not None
        assert result.data.images is not None
        assert isinstance(result.data.images, list)

    @pytest.mark.asyncio
    async def test_scrape_returns_images_with_other_formats(self):
        """Test that scrape can return images alongside other formats."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["markdown", "images"])
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert result.data.images is not None
        assert isinstance(result.data.images, list)

    @pytest.mark.asyncio
    async def test_scrape_returns_branding_when_requested(self):
        """Test that scrape returns branding information when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["branding"])
        assert result.success
        assert result.data is not None
        assert result.data.branding is not None
        # Branding should have at least color_scheme
        assert result.data.branding.color_scheme is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_summary_when_requested(self):
        """Test that scrape returns LLM-generated summary when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["summary"])
        assert result.success
        assert result.data is not None
        # Summary may be None if Ollama is not running, but should not crash
        if result.data.summary is not None:
            assert isinstance(result.data.summary, str)
            assert len(result.data.summary) <= 500  # Max 500 chars per spec

    @pytest.mark.asyncio
    async def test_scrape_returns_summary_with_other_formats(self):
        """Test that scrape can return summary alongside other formats."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["markdown", "summary"])
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        # Summary may be None if Ollama is not running
        if result.data.summary is not None:
            assert isinstance(result.data.summary, str)

    @pytest.mark.asyncio
    async def test_scrape_returns_content_stats(self):
        """Test that scrape returns content_stats with quality metrics."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert result.success
        assert result.data is not None
        assert result.data.content_stats is not None
        assert isinstance(result.data.content_stats, ContentStats)
        assert result.data.content_stats.word_count >= 0
        assert result.data.content_stats.extracted_elements >= 0
        assert isinstance(result.data.content_stats.possible_issues, list)

    @pytest.mark.asyncio
    async def test_scrape_warnings_for_minimal_content(self):
        """Test that scrape returns warnings for pages with minimal content."""
        service = ScrapeService()
        # example.com is intentionally minimal (only ~20 words)
        result = await service.scrape("https://example.com")
        assert result.success
        assert result.data is not None
        # example.com has minimal content, so a warning is expected
        assert result.warnings is not None
        assert len(result.warnings) > 0
        assert "minimal" in result.warnings[0].lower()

    @pytest.mark.asyncio
    async def test_scrape_returns_process_metadata(self):
        """Test that scrape returns process_metadata with scraping info."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert result.success
        assert result.data is not None
        assert result.data.process_metadata is not None
        assert isinstance(result.data.process_metadata, ProcessMetadata)
        # Page load time should be a positive integer
        assert result.data.process_metadata.page_load_time_ms is not None
        assert result.data.process_metadata.page_load_time_ms > 0
        # Default extraction method is main_content
        assert result.data.process_metadata.extraction_method == "main_content"
        # Stealth mode not used for example.com
        assert result.data.process_metadata.stealth_mode_used is False

    @pytest.mark.asyncio
    async def test_scrape_process_metadata_full_page(self):
        """Test that process_metadata reflects full_page extraction."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", only_main_content=False)
        assert result.success
        assert result.data is not None
        assert result.data.process_metadata is not None
        assert result.data.process_metadata.extraction_method == "full_page"


class TestContentQualityHelpers:
    """Unit tests for content quality helper functions."""

    def test_count_extracted_elements_with_paragraphs(self):
        """Test counting elements with paragraphs."""
        html = "<html><body><p>Hello</p><p>World</p><h1>Title</h1></body></html>"
        count = _count_extracted_elements(html)
        assert count == 3  # 2 paragraphs + 1 heading

    def test_count_extracted_elements_with_empty_elements(self):
        """Test that empty elements are not counted."""
        html = "<html><body><p></p><p>  </p><p>Content</p></body></html>"
        count = _count_extracted_elements(html)
        assert count == 1  # Only the paragraph with content

    def test_count_extracted_elements_empty_html(self):
        """Test with empty HTML."""
        assert _count_extracted_elements("") == 0
        assert _count_extracted_elements("<html></html>") == 0

    def test_detect_content_issues_bot_detection(self):
        """Test detection of bot detection patterns."""
        html = "<html><body>Please complete the captcha to continue</body></html>"
        issues = _detect_content_issues(
            status_code=200,
            html=html,
            markdown="Please complete the captcha",
            word_count=5,
            extracted_elements=1,
        )
        assert "bot_detection" in issues

    def test_detect_content_issues_js_heavy(self):
        """Test detection of JavaScript-heavy pages."""
        html = "<html><body><noscript>Please enable JavaScript</noscript></body></html>"
        issues = _detect_content_issues(
            status_code=200,
            html=html,
            markdown="Please enable JavaScript",
            word_count=3,
            extracted_elements=0,
        )
        assert "js_heavy" in issues

    def test_detect_content_issues_extraction_failed(self):
        """Test detection of extraction failure."""
        html = "<html><body><div>X</div></body></html>"
        issues = _detect_content_issues(
            status_code=200,
            html=html,
            markdown="X",
            word_count=1,
            extracted_elements=0,
        )
        assert "extraction_failed" in issues

    def test_detect_content_issues_no_issues(self):
        """Test that good content has no issues detected."""
        html = "<html><body><p>This is good content with many words.</p></body></html>"
        issues = _detect_content_issues(
            status_code=200,
            html=html,
            markdown="This is good content with many words.",
            word_count=200,
            extracted_elements=10,
        )
        assert len(issues) == 0

    def test_generate_content_warnings_minimal_content(self):
        """Test warning generation for minimal content."""
        warnings = _generate_content_warnings(
            status_code=200,
            word_count=23,
            extracted_elements=2,
            possible_issues=["bot_detection"],
            captcha_detected=False,
        )
        assert len(warnings) > 0
        assert "23 words" in warnings[0]
        assert "bot detection" in warnings[0]

    def test_generate_content_warnings_no_warnings_for_good_content(self):
        """Test no warnings for good content."""
        warnings = _generate_content_warnings(
            status_code=200,
            word_count=500,
            extracted_elements=50,
            possible_issues=[],
            captcha_detected=False,
        )
        assert len(warnings) == 0

    def test_generate_content_warnings_captcha(self):
        """Test warning generation for CAPTCHA detection."""
        warnings = _generate_content_warnings(
            status_code=200,
            word_count=10,
            extracted_elements=1,
            possible_issues=[],
            captcha_detected=True,
        )
        assert len(warnings) > 0
        assert any("CAPTCHA" in w for w in warnings)
