"""Tests for adaptive auto-escalation (#129).

The escalation ladder spawns fresh ScrapeService instances internally, each of
which builds its own BrowserManager. These tests patch the BrowserManager the
scrape module constructs so a whole ladder can be driven offline, with each
attempt's response chosen by the engine/stealth the rung used.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from supacrawl.models import QualityVerdict
from supacrawl.services.browser import PageContent, PageMetadata
from supacrawl.services.scrape import ScrapeService

pytestmark = pytest.mark.asyncio

_BLOCKED_HTML = "<html><body><h1>Access Denied</h1><p>You have been blocked.</p></body></html>"
_GOOD_HTML = "<html><body><main><p>" + " ".join(f"word{i}" for i in range(200)) + "</p></main></body></html>"


def _meta() -> PageMetadata:
    return PageMetadata(
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


def _patch_ladder(monkeypatch: pytest.MonkeyPatch, respond, *, patchright=True, camoufox=True) -> list:
    """Patch the scrape module's BrowserManager + engine availability.

    ``respond(engine, stealth)`` returns ``(html, status_code)`` for an attempt.
    Returns a list that records each constructed fake browser (for counting).
    """
    monkeypatch.setattr("supacrawl.services.scrape._is_patchright_available", lambda: patchright)
    monkeypatch.setattr("supacrawl.services.scrape._is_camoufox_available", lambda: camoufox)
    created: list = []

    class FakeBrowser:
        def __init__(self, **kwargs: object) -> None:
            self.engine = kwargs.get("engine")
            self.stealth = bool(kwargs.get("stealth", False))
            self.proxy = kwargs.get("proxy")
            created.append(self)

        async def __aenter__(self) -> "FakeBrowser":
            return self

        async def __aexit__(self, *_: object) -> bool:
            return False

        async def fetch_page(self, url: str, **_: object) -> PageContent:
            html, status = respond(self.engine, self.stealth)
            return PageContent(url=url, html=html, title="T", status_code=status)

        async def extract_metadata(self, _html: str) -> PageMetadata:
            return _meta()

    monkeypatch.setattr("supacrawl.services.scrape.BrowserManager", FakeBrowser)
    return created


async def test_auto_escalation_recovers_blocked_page(monkeypatch: pytest.MonkeyPatch) -> None:
    # Cheap playwright attempt is blocked; the stealth rung returns real content.
    def respond(engine: str | None, stealth: bool) -> tuple[str, int]:
        if stealth or engine == "camoufox":
            return _GOOD_HTML, 200
        return _BLOCKED_HTML, 403

    created = _patch_ladder(monkeypatch, respond)
    result = await ScrapeService().scrape("https://x.example", formats=["markdown"], http_first=False)

    assert result.success is True
    assert result.data is not None and result.data.markdown and "word10" in result.data.markdown
    assert result.quality is not None
    assert result.quality.verdict == QualityVerdict.OK
    assert result.quality.escalated is True
    assert result.quality.attempts >= 2
    assert len(created) >= 2  # at least one escalation happened


async def test_escalation_budget_bounds_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every rung stays blocked: the ladder must stop at the bounded budget.
    created = _patch_ladder(monkeypatch, lambda engine, stealth: (_BLOCKED_HTML, 403))
    result = await ScrapeService().scrape("https://x.example", formats=["markdown"], http_first=False)

    assert result.success is False
    assert result.quality is not None
    # playwright -> patchright -> camoufox -> camoufox+HTTP/1.1 == 4 attempts, no more.
    assert result.quality.attempts == 4
    assert len(created) == 4


async def test_escalate_false_takes_a_single_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _patch_ladder(monkeypatch, lambda engine, stealth: (_BLOCKED_HTML, 403))
    result = await ScrapeService().scrape("https://x.example", formats=["markdown"], http_first=False, escalate=False)

    assert result.success is False
    assert result.quality is not None and result.quality.attempts == 1
    assert result.quality.escalated is False
    assert len(created) == 1


async def test_no_escalation_when_no_stealth_engine_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Honest dead-end: blocked, and nothing stronger is installed to escalate to.
    created = _patch_ladder(monkeypatch, lambda engine, stealth: (_BLOCKED_HTML, 403), patchright=False, camoufox=False)
    result = await ScrapeService().scrape("https://x.example", formats=["markdown"], http_first=False)

    assert result.success is False
    assert result.quality is not None and result.quality.verdict == QualityVerdict.BOT_CHALLENGE
    assert len(created) == 1


async def test_thin_main_content_falls_back_to_full_page() -> None:
    # When only_main_content extraction is anomalously sparse, the fuller page is
    # recovered rather than silently dropping the real content.
    service = ScrapeService()
    rich_body = " ".join(f"word{i}" for i in range(200))
    html = f"<html><body><p>{rich_body}</p></body></html>"
    recovered = service._recover_thin_main_content(
        html=html,
        main_markdown="tiny bit",
        url="https://x.example",
        exclude_tags=None,
        content_mode=0.5,
        query=None,
    )
    assert len(recovered.split()) >= 50


async def test_strategy_memory_seeds_the_ladder(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # The first hit climbs the ladder; the second hit to the same domain is
    # seeded straight to the winning strategy, taking a single attempt (#130).
    from supacrawl.services.strategy_memory import StrategyStore

    def respond(engine: str | None, stealth: bool) -> tuple[str, int]:
        if stealth or engine == "camoufox":
            return _GOOD_HTML, 200
        return _BLOCKED_HTML, 403

    created = _patch_ladder(monkeypatch, respond)
    store = StrategyStore(strategy_dir=tmp_path, explore_rate=0.0)

    r1 = await ScrapeService(strategy_store=store).scrape(
        "https://airline.example/a", formats=["markdown"], http_first=False
    )
    assert r1.success is True
    assert len(created) >= 2  # the first hit had to escalate to find the winner

    created.clear()
    r2 = await ScrapeService(strategy_store=store).scrape(
        "https://airline.example/b", formats=["markdown"], http_first=False
    )
    assert r2.success is True
    assert len(created) == 1  # seeded straight to the champion — no ladder walk
    assert r2.quality is not None
    assert r2.quality.attempts == 1
    assert r2.quality.escalated is False


async def test_strategy_memory_disabled_is_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no store, behaviour is the plain stateless ladder (no seeding/recording).
    created = _patch_ladder(monkeypatch, lambda engine, stealth: (_GOOD_HTML, 200))
    result = await ScrapeService(strategy_store=None).scrape(
        "https://x.example", formats=["markdown"], http_first=False
    )
    assert result.success is True
    assert len(created) == 1


async def test_fetch_exception_yields_clean_failure_not_crash() -> None:
    # A mid-fetch exception must become success=False with a hint, never a crash.
    browser = MagicMock()
    browser.engine = "playwright"
    browser.fetch_page = AsyncMock(side_effect=TimeoutError("Page.goto: Timeout 30000ms exceeded"))
    service = ScrapeService(browser=browser)

    result = await service.scrape("https://x.example", formats=["markdown"], http_first=False)

    assert result.success is False
    assert result.error is not None and "timeout" in result.error.lower()
    assert result.quality is not None  # a structured verdict accompanies the failure
