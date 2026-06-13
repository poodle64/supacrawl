"""Tests for agent-readable, remediation-shaped errors (#123)."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from supacrawl.services.browser import PageContent, PageMetadata
from supacrawl.services.remediation import remediation_hint, thin_content_hint
from supacrawl.services.scrape import ScrapeService


class TestRemediationHint:
    """Error string -> concrete, honest recovery hint."""

    def test_timeout(self) -> None:
        hint = remediation_hint("Page.goto: Timeout 30000ms exceeded")
        assert hint is not None and "timeout" in hint.lower()

    def test_dns_failure(self) -> None:
        hint = remediation_hint("net::ERR_NAME_NOT_RESOLVED at https://nope.invalid")
        assert hint is not None and "resolve" in hint.lower()

    def test_connection_refused(self) -> None:
        hint = remediation_hint("net::ERR_CONNECTION_REFUSED")
        assert hint is not None and ("refused" in hint.lower() or "reset" in hint.lower())

    def test_tls_error(self) -> None:
        hint = remediation_hint("net::ERR_CERT_DATE_INVALID")
        assert hint is not None and ("tls" in hint.lower() or "certificate" in hint.lower())

    def test_not_found(self) -> None:
        hint = remediation_hint("HTTP 404 Not Found")
        assert hint is not None and "404" in hint

    def test_server_error(self) -> None:
        hint = remediation_hint("HTTP 503 Service Unavailable")
        assert hint is not None and "5xx" in hint

    def test_no_hint_for_unknown(self) -> None:
        # No speculative advice when nothing specific applies (the #107 lesson).
        assert remediation_hint("some completely unrecognised failure") is None


class TestThinContentHint:
    def test_main_content_suggests_disabling_it(self) -> None:
        assert "only_main_content=False" in thin_content_hint(only_main_content=True)

    def test_full_page_suggests_wait_or_auth(self) -> None:
        hint = thin_content_hint(only_main_content=False)
        assert "only_main_content" not in hint
        assert "wait_for" in hint


class TestMapExceptionRemediation:
    """map_exception attaches a remediation hint when one applies."""

    def test_timeout_exception_gets_hint(self) -> None:
        from supacrawl.mcp.exceptions import SupacrawlTimeoutError, map_exception

        err = map_exception(httpx.TimeoutException("Request timed out after 30s"), endpoint="/scrape")
        assert isinstance(err, SupacrawlTimeoutError)
        assert "[HINT:" in err.message

    def test_connect_error_gets_hint(self) -> None:
        from supacrawl.mcp.exceptions import map_exception

        err = map_exception(httpx.ConnectError("net::ERR_CONNECTION_REFUSED"))
        assert "[HINT:" in err.message

    def test_validation_error_gets_no_spurious_hint(self) -> None:
        from supacrawl.exceptions import ValidationError as LibValidationError
        from supacrawl.mcp.exceptions import map_exception

        err = map_exception(LibValidationError("entrypoints required"))
        assert "[HINT:" not in err.message


@pytest.mark.asyncio
class TestSoftWarningCarriesRemediation:
    """A thin page is served with a warning that includes a recovery action."""

    async def test_low_density_page_warning_has_hint(self) -> None:
        # Large markup, almost no text: structurally valid (not a JS shell) but
        # low density -> SOFT content-quality warning on the browser path.
        html = "<html><body>" + ("<div></div>" * 500) + "<p>hello world test</p></body></html>"
        browser = MagicMock()
        browser.engine = "playwright"
        browser.fetch_page = AsyncMock(
            return_value=PageContent(url="https://x.example", html=html, title="T", status_code=200)
        )
        browser.extract_metadata = AsyncMock(
            return_value=PageMetadata(
                title="T",
                description=None,
                language=None,
                keywords=None,
                robots=None,
                canonical_url=None,
                og_title=None,
                og_description=None,
                og_image=None,
                og_url=None,
                og_site_name=None,
            )
        )

        service = ScrapeService(browser=browser)
        result = await service.scrape("https://x.example", formats=["markdown"], http_first=False)

        assert result.success
        assert result.warnings is not None
        assert any("only_main_content=False" in w for w in result.warnings)
