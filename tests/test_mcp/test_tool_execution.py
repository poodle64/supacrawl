"""Tests for Supacrawl MCP tool execution."""

import pytest


class TestScrapeTools:
    """Test scrape-related tools."""

    @pytest.mark.asyncio
    async def test_scrape_single_url(self, mock_api_client):
        """Scrape tool should call service with correct parameters."""
        from supacrawl.mcp.tools.scrape import supacrawl_scrape

        result = await supacrawl_scrape(
            api_client=mock_api_client,
            url="https://example.com",
            formats=["markdown"],
            only_main_content=True,
        )

        assert result["success"] is True
        mock_api_client.scrape_service.scrape.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_returns_content(self, mock_api_client):
        """Scrape tool should return markdown content."""
        from supacrawl.mcp.tools.scrape import supacrawl_scrape

        result = await supacrawl_scrape(
            api_client=mock_api_client,
            url="https://example.com",
        )

        assert result["success"] is True
        assert "data" in result


class TestSearchTools:
    """Test search-related tools."""

    @pytest.mark.asyncio
    async def test_search_basic_query(self, mock_api_client):
        """Search tool should call service with query."""
        from supacrawl.mcp.tools.search import supacrawl_search

        result = await supacrawl_search(
            api_client=mock_api_client,
            query="test query",
            limit=5,
        )

        assert result["success"] is True
        mock_api_client.search_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_scrape(self, mock_api_client):
        """Search tool should support scraping results."""
        from supacrawl.mcp.tools.search import supacrawl_search

        result = await supacrawl_search(
            api_client=mock_api_client,
            query="test query",
            scrape_results=True,
            formats=["markdown"],
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_with_include_metadata(self, mock_api_client, monkeypatch):
        """Search tool should fetch metadata via HEAD requests when include_metadata=True."""
        from supacrawl.mcp.tools import search as search_module
        from supacrawl.mcp.tools.search import supacrawl_search

        # Mock the metadata fetcher to return predictable results
        async def mock_fetch_metadata(url, timeout=5.0):
            return {
                "content_type": "text/html",
                "content_length": 12345,
            }

        monkeypatch.setattr(search_module, "_fetch_url_metadata", mock_fetch_metadata)

        result = await supacrawl_search(
            api_client=mock_api_client,
            query="test query",
            include_metadata=True,
        )

        assert result["success"] is True
        assert "data" in result
        # Web results should have metadata added
        for item in result["data"]:
            if item.get("source_type") == "web":
                assert "metadata" in item
                assert item["metadata"]["content_type"] == "text/html"
                assert item["metadata"]["content_length"] == 12345

    @pytest.mark.asyncio
    async def test_search_metadata_not_fetched_when_scraping(self, mock_api_client, monkeypatch):
        """Metadata should not be fetched when scrape_results=True (scraping includes richer metadata)."""
        from supacrawl.mcp.tools import search as search_module
        from supacrawl.mcp.tools.search import supacrawl_search

        fetch_called = False

        async def mock_fetch_metadata(url, timeout=5.0):
            nonlocal fetch_called
            fetch_called = True
            return {"content_type": "text/html"}

        monkeypatch.setattr(search_module, "_fetch_url_metadata", mock_fetch_metadata)

        await supacrawl_search(
            api_client=mock_api_client,
            query="test query",
            include_metadata=True,
            scrape_results=True,  # Scraping takes precedence
        )

        assert not fetch_called, "Metadata fetch should be skipped when scraping is enabled"


class TestExtractTools:
    """Test extract-related tools."""

    @pytest.mark.asyncio
    async def test_extract_with_prompt(self, mock_api_client):
        """Extract tool should scrape and return content with extraction context."""
        from supacrawl.mcp.tools.extract import supacrawl_extract

        result = await supacrawl_extract(
            api_client=mock_api_client,
            urls=["https://example.com"],
            prompt="Extract the title",
        )

        assert result["success"] is True
        assert "data" in result
        assert "extraction_context" in result
        assert result["extraction_context"]["prompt"] == "Extract the title"
        # Extract now uses scrape_service, not extract_service
        mock_api_client.scrape_service.scrape.assert_called()

    @pytest.mark.asyncio
    async def test_extract_with_schema(self, mock_api_client):
        """Extract tool should return schema in extraction context."""
        from supacrawl.mcp.tools.extract import supacrawl_extract

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        result = await supacrawl_extract(
            api_client=mock_api_client,
            urls=["https://example.com"],
            schema=schema,
        )

        assert result["success"] is True
        assert result["extraction_context"]["schema"] == schema


class TestSummaryTools:
    """Test summary-related tools."""

    @pytest.mark.asyncio
    async def test_summary_basic(self, mock_api_client):
        """Summary tool should scrape and return content with summary context."""
        from supacrawl.mcp.tools.summary import supacrawl_summary

        result = await supacrawl_summary(
            api_client=mock_api_client,
            url="https://example.com",
        )

        assert result["success"] is True
        assert "data" in result
        assert "summary_context" in result
        mock_api_client.scrape_service.scrape.assert_called()

    @pytest.mark.asyncio
    async def test_summary_with_focus(self, mock_api_client):
        """Summary tool should include focus in context."""
        from supacrawl.mcp.tools.summary import supacrawl_summary

        result = await supacrawl_summary(
            api_client=mock_api_client,
            url="https://example.com",
            focus="technical details",
            max_length=100,
        )

        assert result["success"] is True
        assert result["summary_context"]["focus"] == "technical details"
        assert result["summary_context"]["max_length"] == 100


class TestMapTools:
    """Test map-related tools."""

    @pytest.mark.asyncio
    async def test_map_basic(self, mock_api_client):
        """Map tool should discover URLs."""
        from supacrawl.mcp.tools.map import supacrawl_map

        result = await supacrawl_map(
            api_client=mock_api_client,
            url="https://example.com",
        )

        assert result["success"] is True
        mock_api_client.map_service.map_all.assert_called_once()


class TestCrawlTools:
    """Test crawl-related tools."""

    @pytest.mark.asyncio
    async def test_crawl_basic(self, mock_api_client):
        """Crawl tool should discover and scrape pages."""
        from supacrawl.mcp.tools.crawl import supacrawl_crawl

        result = await supacrawl_crawl(
            api_client=mock_api_client,
            url="https://example.com",
            limit=10,
        )

        assert result["success"] is True
        assert result["status"] == "completed"


class TestDiagnoseTools:
    """Test diagnose-related tools."""

    @pytest.mark.asyncio
    async def test_diagnose_detection_functions(self):
        """Test internal detection functions."""
        from supacrawl.mcp.tools.diagnose import (
            _detect_bot_protection,
            _detect_cdn,
            _detect_js_framework,
            _detect_login_required,
        )

        # Test CDN detection
        assert _detect_cdn({"cf-ray": "abc123"}) == "cloudflare"
        assert _detect_cdn({"server": "cloudflare"}) == "cloudflare"
        assert _detect_cdn({"x-akamai-transformed": "1"}) == "akamai"
        assert _detect_cdn({"x-amz-cf-id": "xyz"}) == "aws_cloudfront"
        assert _detect_cdn({"content-type": "text/html"}) is None

        # Test JS framework detection
        assert _detect_js_framework('<div id="root"></div>') == "react"
        assert _detect_js_framework("__NEXT_DATA__") == "react"
        assert _detect_js_framework("__NUXT__") == "vue"
        assert _detect_js_framework("<app-root></app-root>") == "angular"
        assert _detect_js_framework("<html><body>Plain</body></html>") is None

        # Test bot protection detection
        result = _detect_bot_protection("g-recaptcha")
        assert result["captcha_present"] is True

        result = _detect_bot_protection("just a moment")
        assert result["challenge_detected"] is True

        result = _detect_bot_protection("Access Denied")
        assert result["access_denied"] is True

        # Test login detection
        assert _detect_login_required('type="password"') is True
        assert _detect_login_required("Sign in to continue") is True
        assert _detect_login_required("<html><body>Normal page</body></html>") is False

    @pytest.mark.asyncio
    async def test_diagnose_recommendations(self):
        """Test recommendation generation."""
        from supacrawl.mcp.tools.diagnose import _generate_recommendations

        # Cloudflare detected
        recs = _generate_recommendations(
            cdn="cloudflare",
            framework=None,
            bot_indicators={"challenge_detected": True},
            requires_js=False,
            login_required=False,
        )
        assert recs.get("stealth_mode") is True
        assert recs.get("wait_for", 0) >= 5000

        # React SPA detected
        recs = _generate_recommendations(
            cdn=None,
            framework="react",
            bot_indicators={},
            requires_js=True,
            login_required=False,
        )
        assert recs.get("wait_for", 0) >= 3000

        # CAPTCHA detected
        recs = _generate_recommendations(
            cdn=None,
            framework=None,
            bot_indicators={"captcha_present": True},
            requires_js=False,
            login_required=False,
        )
        assert recs.get("captcha_solving") is True

        # No issues
        recs = _generate_recommendations(
            cdn=None,
            framework=None,
            bot_indicators={},
            requires_js=False,
            login_required=False,
        )
        assert "No issues detected" in recs.get("reason", "")
