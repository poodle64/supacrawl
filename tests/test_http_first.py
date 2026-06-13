"""Tests for the HTTP-first fast path (#119).

Covers the eligibility gate, the escalation decision (when a cheap GET is not
enough and the browser must take over), and the offline assembly of a result
from static HTML. The fast path's network call is monkeypatched throughout so
these stay unit tests.
"""

import pytest

from supacrawl.services.detection import estimate_js_requirement
from supacrawl.services.http_fetch import HttpFetchResult
from supacrawl.services.scrape import ScrapeService

# A well-formed static article: real <title>, a heading, and dense body text.
GOOD_HTML = (
    "<html><head><title>Example Domain</title>"
    '<meta name="description" content="An illustrative page."></head>'
    "<body><main><h1>Hello</h1><p>" + ("word " * 80) + "</p></main></body></html>"
)
# A React/Next.js shell: framework markers, empty root, no real body text.
JS_SHELL = (
    "<html><head><title>App</title></head><body>"
    '<div id="root"></div><script src="/_next/static/chunks/app.js"></script>'
    "</body></html>"
)
# A Cloudflare-style interstitial.
BOT_HTML = "<html><body><h1>Just a moment...</h1><p>Checking your browser before accessing.</p></body></html>"


def _fetched(html: str, status: int = 200) -> HttpFetchResult:
    return HttpFetchResult(
        url="https://example.com",
        html=html,
        status_code=status,
        content_type="text/html",
        headers={},
    )


class TestEstimateJsRequirement:
    """The render-needed heuristic that gates escalation."""

    def test_static_article_does_not_need_js(self) -> None:
        assert estimate_js_requirement(GOOD_HTML, len(GOOD_HTML)) is False

    def test_framework_shell_needs_js(self) -> None:
        assert estimate_js_requirement(JS_SHELL, len(JS_SHELL)) is True

    def test_empty_body_needs_js(self) -> None:
        html = "<html><body>   </body></html>"
        assert estimate_js_requirement(html, len(html)) is True


class TestHttpFirstEligible:
    """The cheap-path gate on ScrapeService."""

    def test_eligible_for_plain_markdown(self) -> None:
        assert ScrapeService()._http_first_eligible(["markdown"], None, None, None) is True

    def test_eligible_with_explicit_playwright_engine(self) -> None:
        assert ScrapeService()._http_first_eligible(["markdown"], None, "playwright", None) is True

    def test_ineligible_for_screenshot(self) -> None:
        assert ScrapeService()._http_first_eligible(["screenshot"], None, None, None) is False

    def test_ineligible_for_pdf_capture(self) -> None:
        assert ScrapeService()._http_first_eligible(["pdf"], None, None, None) is False

    def test_ineligible_with_actions(self) -> None:
        assert ScrapeService()._http_first_eligible(["markdown"], [{"type": "wait"}], None, None) is False

    def test_ineligible_with_device(self) -> None:
        assert ScrapeService()._http_first_eligible(["markdown"], None, None, "iPhone 14") is False

    def test_ineligible_with_stealth(self) -> None:
        assert ScrapeService(stealth=True)._http_first_eligible(["markdown"], None, None, None) is False

    def test_ineligible_with_camoufox_engine(self) -> None:
        assert ScrapeService()._http_first_eligible(["markdown"], None, "camoufox", None) is False

    def test_ineligible_with_service_default_engine(self) -> None:
        assert ScrapeService(engine="patchright")._http_first_eligible(["markdown"], None, None, None) is False


@pytest.mark.asyncio
class TestTryHttpFirst:
    """The escalate-or-serve decision after a static fetch."""

    async def _run(self, monkeypatch: pytest.MonkeyPatch, fetched: HttpFetchResult | None, **overrides: object):
        async def fake_fetch(url: str, **kwargs: object) -> HttpFetchResult | None:
            return fetched

        monkeypatch.setattr("supacrawl.services.scrape.fetch_static", fake_fetch)
        service = ScrapeService()
        kwargs: dict[str, object] = {
            "url": "https://example.com",
            "formats": ["markdown"],
            "timeout": 30000,
            "only_main_content": True,
            "include_tags": None,
            "exclude_tags": None,
            "content_mode": 0.5,
            "query": None,
            "expand_iframes": "same-origin",
            "headers": None,
            "proxy": None,
            "json_schema": None,
            "json_prompt": None,
            "wants_change_tracking": False,
            "previous_entry": None,
            "change_tracking_modes": None,
            "max_age": 0,
            "cache_variant": None,
        }
        kwargs.update(overrides)
        return await service._try_http_first(**kwargs)  # type: ignore[arg-type]

    async def test_page_with_robots_meta_is_served(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: a normal page carrying ``<meta name="robots">`` (matched by
        the bot-detection regex via the substring "robot") must still be served —
        the density heuristic must use the real word count, not a hard zero."""
        html = (
            '<html><head><title>Article</title><meta name="robots" content="index,follow">'
            "</head><body><main><h1>Headline</h1><p>" + ("word " * 80) + "</p></main></body></html>"
        )
        result = await self._run(monkeypatch, _fetched(html))
        assert result is not None
        assert result.success
        assert result.data is not None
        assert result.data.markdown and "Headline" in result.data.markdown

    async def test_links_only_page_with_robots_meta_is_served(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Same regression for a non-markdown format, where markdown is not computed
        and the visible-text fallback must supply the word count."""
        html = (
            '<html><head><title>Links</title><meta name="robots" content="all"></head>'
            "<body><main><a href='/a'>A</a><p>" + ("word " * 80) + "</p></main></body></html>"
        )
        result = await self._run(monkeypatch, _fetched(html), formats=["links"])
        assert result is not None
        assert result.success

    async def test_static_page_served_without_browser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await self._run(monkeypatch, _fetched(GOOD_HTML))
        assert result is not None
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert "Hello" in result.data.markdown
        assert result.data.metadata.title == "Example Domain"
        assert result.data.metadata.source_url == "https://example.com"
        assert result.data.metadata.status_code == 200

    async def test_js_shell_escalates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert await self._run(monkeypatch, _fetched(JS_SHELL)) is None

    async def test_bot_challenge_escalates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert await self._run(monkeypatch, _fetched(BOT_HTML)) is None

    async def test_blocking_status_escalates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert await self._run(monkeypatch, _fetched(GOOD_HTML, status=403)) is None

    async def test_fetch_failure_escalates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert await self._run(monkeypatch, None) is None

    async def test_iframe_page_escalates_when_expansion_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = "<html><body><iframe src='https://x.example'></iframe><p>" + ("word " * 80) + "</p></body></html>"
        assert await self._run(monkeypatch, _fetched(html), expand_iframes="same-origin") is None

    async def test_iframe_page_served_when_expansion_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = (
            "<html><head><title>Embed</title></head><body><iframe src='https://x.example'></iframe>"
            "<main><p>" + ("word " * 80) + "</p></main></body></html>"
        )
        result = await self._run(monkeypatch, _fetched(html), expand_iframes="none")
        assert result is not None
        assert result.success

    async def test_links_format_served_without_markdown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = (
            "<html><head><title>Links</title></head><body><main>"
            '<a href="/a">A</a><a href="https://other.example/b">B</a>'
            "<p>" + ("word " * 80) + "</p></main></body></html>"
        )
        result = await self._run(monkeypatch, _fetched(html), formats=["links"])
        assert result is not None
        assert result.data is not None
        assert result.data.links is not None
        assert "https://example.com/a" in result.data.links
