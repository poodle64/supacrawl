"""A dead shared browser engine must be visible on the health surface (#160).

The reported outage was silent: a long-lived sidecar's browser pool had died and
nothing said so, so every consumer on the box got failing scrapes until a human
happened to notice. Configuration alone can never show this — only a live read of
the engine can — and it has to reach the top-line verdict, not sit one level down
where a caller checking ``status`` would miss it.
"""

from __future__ import annotations

from typing import Any

import pytest

from supacrawl.mcp.tools.health import supacrawl_health

pytestmark = pytest.mark.asyncio


class _StubBrowser:
    def __init__(self, *, alive: bool, relaunches: int = 0) -> None:
        self.is_alive = alive
        self.relaunches = relaunches
        self.engine = "playwright"


class _StubServices:
    """Stand-in for SupacrawlServices with everything but the browser healthy."""

    def __init__(self, browser_manager: Any) -> None:
        self.browser_manager = browser_manager
        self.search_service = None

    def get_service_status(self) -> dict[str, bool]:
        return {"scrape": True, "crawl": True, "map": True, "search": True}


@pytest.fixture(autouse=True)
def _healthy_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep search out of the verdict so browser liveness is the only variable."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")


async def test_a_dead_engine_makes_the_server_report_degraded() -> None:
    result = await supacrawl_health(_StubServices(_StubBrowser(alive=False)), verify_search=False)  # type: ignore[arg-type]

    assert result["status"] == "degraded", "a dead browser pool read as healthy"
    browser = result["components"]["browser"]
    assert browser["alive"] is False
    assert "restart" in browser["warning"].lower()


async def test_a_live_engine_reports_healthy_and_its_relaunch_count() -> None:
    result = await supacrawl_health(_StubServices(_StubBrowser(alive=True, relaunches=2)), verify_search=False)  # type: ignore[arg-type]

    assert result["status"] == "healthy"
    browser = result["components"]["browser"]
    assert browser["alive"] is True
    # A climbing count is the signal that something keeps killing the engine even
    # though each individual scrape recovered.
    assert browser["relaunches"] == 2
    assert "warning" not in browser


async def test_a_server_with_no_shared_engine_reports_no_liveness_claim() -> None:
    result = await supacrawl_health(_StubServices(None), verify_search=False)  # type: ignore[arg-type]

    assert "alive" not in result["components"]["browser"]
    assert result["status"] == "healthy"
