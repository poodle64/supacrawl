"""Tests for the expect-content gate (#121)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from supacrawl.services.browser import PageContent, PageMetadata
from supacrawl.services.http_fetch import HttpFetchResult
from supacrawl.services.scrape import ScrapeService


def _mock_browser(html: str) -> MagicMock:
    """A BrowserManager stand-in whose fetch returns *html* and parses metadata."""
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
    return browser


PRICE_HTML = (
    "<html><head><title>Product</title></head><body><main>"
    '<h1>Widget</h1><span class="price">$19.99</span>'
    "<p>" + ("word " * 60) + "In stock now.</p></main></body></html>"
)


def _fetched(html: str, status: int = 200) -> HttpFetchResult:
    return HttpFetchResult(
        url="https://shop.example", html=html, status_code=status, content_type="text/html", headers={}
    )


class TestExpectSatisfied:
    """The three-mode assertion: word count, CSS selector, text substring."""

    def test_min_word_count_met(self) -> None:
        assert ScrapeService._expect_satisfied(PRICE_HTML, "word " * 60, "50") is True

    def test_min_word_count_unmet(self) -> None:
        assert ScrapeService._expect_satisfied("<html><body><p>two words</p></body></html>", "two words", "50") is False

    def test_css_selector_matches(self) -> None:
        assert ScrapeService._expect_satisfied(PRICE_HTML, None, ".price") is True

    def test_css_selector_absent(self) -> None:
        assert ScrapeService._expect_satisfied(PRICE_HTML, None, ".out-of-stock") is False

    def test_text_substring_present(self) -> None:
        assert ScrapeService._expect_satisfied(PRICE_HTML, None, "In stock") is True

    def test_text_substring_absent(self) -> None:
        assert ScrapeService._expect_satisfied(PRICE_HTML, None, "Sold out") is False

    def test_text_match_uses_visible_text_not_attributes(self) -> None:
        # "price" appears only as a class attribute, not visible text → not matched as text.
        html = '<html><body><div class="price">$5</div></body></html>'
        assert ScrapeService._expect_satisfied(html, None, "expensive") is False

    def test_none_always_satisfied(self) -> None:
        assert ScrapeService._expect_satisfied(PRICE_HTML, None, None) is True


class TestExpectSelector:
    """Only selector-shaped (single-token, structural-char) expectations become a browser wait."""

    def test_class_selector_is_selector(self) -> None:
        assert ScrapeService._expect_selector(".product") == ".product"

    def test_id_selector_is_selector(self) -> None:
        assert ScrapeService._expect_selector("#main") == "#main"

    def test_attribute_selector_is_selector(self) -> None:
        assert ScrapeService._expect_selector("[data-loaded]") == "[data-loaded]"

    def test_free_text_is_not_selector(self) -> None:
        assert ScrapeService._expect_selector("Add to cart") is None

    def test_text_with_period_is_not_selector(self) -> None:
        # Has a structural char but also a space → treated as text, not a wait target.
        assert ScrapeService._expect_selector("Price: $19.99 today") is None

    def test_word_count_is_not_selector(self) -> None:
        assert ScrapeService._expect_selector("200") is None

    def test_bare_tag_is_not_a_wait_selector(self) -> None:
        # SPA stability already waits for common tags; a bare word stays text-mode.
        assert ScrapeService._expect_selector("main") is None


@pytest.mark.asyncio
class TestHttpFirstExpectEscalation:
    """An unmet expectation makes the HTTP-first path escalate to the browser."""

    async def _run(self, monkeypatch: pytest.MonkeyPatch, fetched: HttpFetchResult, expect: str):
        async def fake_fetch(url: str, **kwargs: object) -> HttpFetchResult:
            return fetched

        monkeypatch.setattr("supacrawl.services.scrape.fetch_static", fake_fetch)
        return await ScrapeService()._try_http_first(
            url="https://shop.example",
            formats=["markdown"],
            timeout=30000,
            only_main_content=True,
            include_tags=None,
            exclude_tags=None,
            content_mode=0.5,
            query=None,
            expand_iframes="same-origin",
            headers=None,
            proxy=None,
            json_schema=None,
            json_prompt=None,
            wants_change_tracking=False,
            previous_entry=None,
            change_tracking_modes=None,
            max_age=0,
            cache_variant=None,
            expect=expect,
            parse_pdf=None,
        )

    async def test_met_expectation_served(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await self._run(monkeypatch, _fetched(PRICE_HTML), ".price")
        assert result is not None
        assert result.success

    async def test_unmet_expectation_escalates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await self._run(monkeypatch, _fetched(PRICE_HTML), ".reviews-loaded")
        assert result is None


@pytest.mark.asyncio
class TestBrowserPathExpectGate:
    """The browser-path gate: served when met, first-class failure when not."""

    async def test_browser_path_serves_when_expectation_met(self) -> None:
        service = ScrapeService(browser=_mock_browser(PRICE_HTML))
        result = await service.scrape("https://x.example", formats=["markdown"], http_first=False, expect=".price")
        assert result.success
        assert result.data is not None
        assert result.data.markdown and "Widget" in result.data.markdown

    async def test_browser_path_fails_first_class_without_patchright(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No stealth retry possible -> honest, first-class failure (not a skeleton).
        monkeypatch.setattr("supacrawl.services.scrape._is_patchright_available", lambda: False)
        service = ScrapeService(browser=_mock_browser(PRICE_HTML))
        result = await service.scrape("https://x.example", formats=["markdown"], http_first=False, expect=".absent-xyz")
        assert result.success is False
        assert result.error is not None
        assert "Expected content not found" in result.error
        # The message must reflect what was actually tried (no false "stealth retry" claim).
        assert "supacrawl[stealth]" in result.error
        assert "correlation_id=" in result.error
