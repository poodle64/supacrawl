"""Unit tests for the live search health probe (#156).

``_get_search_config`` only ever checked that a provider was *configured*
(``is_available()``), never that a search actually returns results — the
exact gap that let SearXNG's multi-word query bug report "healthy" while
every real search came back empty. These tests cover the probe helper and
its effect on ``supacrawl_health``'s reported status.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from supacrawl.mcp.tools import health as health_module
from supacrawl.mcp.tools.health import _run_search_health_probe, supacrawl_health

pytestmark = pytest.mark.mcp

_SETTINGS_PATH = "supacrawl.mcp.tools.health.settings"


def _settings_kwargs(**overrides):
    base = {"search_providers": None, "search_provider": "brave", "search_rate_limit": None}
    base.update(overrides)
    return base


def _make_search_service(*, success: bool, data: list, error: str | None = None) -> MagicMock:
    """A search_service double whose .search() resolves to a canned SearchResult."""
    svc = MagicMock(spec=["search"])
    svc.search = AsyncMock(return_value=MagicMock(success=success, data=data, error=error))
    return svc


class TestRunSearchHealthProbe:
    """Tests for _run_search_health_probe() in isolation."""

    @pytest.mark.asyncio
    async def test_returns_none_without_search_service(self) -> None:
        assert await _run_search_health_probe(None) is None

    @pytest.mark.asyncio
    async def test_returns_none_when_service_has_no_search_method(self) -> None:
        assert await _run_search_health_probe(MagicMock(spec=[])) is None

    @pytest.mark.asyncio
    async def test_ok_true_when_probe_returns_results(self) -> None:
        svc = _make_search_service(success=True, data=[MagicMock()])

        probe = await _run_search_health_probe(svc)

        assert probe == {"probed": True, "ok": True, "result_count": 1, "error": None}
        svc.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ok_false_when_probe_returns_empty_results(self) -> None:
        """The regression #156 exists to catch: success=True but zero results."""
        svc = _make_search_service(success=True, data=[])

        probe = await _run_search_health_probe(svc)
        assert probe is not None

        assert probe["ok"] is False
        assert probe["result_count"] == 0

    @pytest.mark.asyncio
    async def test_ok_false_when_search_reports_failure(self) -> None:
        svc = _make_search_service(success=False, data=[], error="No usable search provider.")

        probe = await _run_search_health_probe(svc)
        assert probe is not None

        assert probe["ok"] is False
        assert probe["error"] == "No usable search provider."

    @pytest.mark.asyncio
    async def test_ok_false_when_search_raises(self) -> None:
        svc = MagicMock(spec=["search"])
        svc.search = AsyncMock(side_effect=RuntimeError("upstream exploded"))

        probe = await _run_search_health_probe(svc)

        assert probe == {"probed": True, "ok": False, "result_count": 0, "error": "upstream exploded"}

    @pytest.mark.asyncio
    async def test_times_out_instead_of_hanging(self) -> None:
        import asyncio

        async def _hang(*_args, **_kwargs):
            await asyncio.sleep(10)

        svc = MagicMock(spec=["search"])
        svc.search = AsyncMock(side_effect=_hang)

        with patch.object(health_module, "_SEARCH_PROBE_TIMEOUT_S", 0.01):
            probe = await _run_search_health_probe(svc)

        assert probe is not None
        assert probe["ok"] is False
        assert probe["probed"] is True


class TestSupacrawlHealthLiveProbeIntegration:
    """Tests for how the probe folds into supacrawl_health()'s overall status."""

    def _api_client(self, search_service: MagicMock) -> MagicMock:
        client = MagicMock()
        client.get_service_status.return_value = {
            "browser": True,
            "scrape": True,
            "crawl": True,
            "map": True,
            "search": True,
        }
        client.search_service = search_service
        return client

    @pytest.mark.asyncio
    async def test_default_runs_probe_and_downgrades_on_empty_results(self) -> None:
        svc = _make_search_service(success=True, data=[])
        client = self._api_client(svc)

        with patch(_SETTINGS_PATH, **_settings_kwargs()), patch.dict("os.environ", {"BRAVE_API_KEY": "k"}):
            result = await supacrawl_health(client)

        svc.search.assert_awaited_once()
        assert result["status"] == "degraded"
        assert result["components"]["search"]["status"] == "degraded"
        assert result["components"]["search"]["live_probe"]["ok"] is False
        assert "Live search probe" in result["components"]["search"]["warning"]

    @pytest.mark.asyncio
    async def test_healthy_when_probe_finds_results(self) -> None:
        svc = _make_search_service(success=True, data=[MagicMock()])
        client = self._api_client(svc)

        with patch(_SETTINGS_PATH, **_settings_kwargs()), patch.dict("os.environ", {"BRAVE_API_KEY": "k"}):
            result = await supacrawl_health(client)

        assert result["status"] == "healthy"
        assert result["components"]["search"]["live_probe"]["ok"] is True

    @pytest.mark.asyncio
    async def test_verify_search_false_skips_the_live_call(self) -> None:
        svc = _make_search_service(success=True, data=[])
        client = self._api_client(svc)

        with patch(_SETTINGS_PATH, **_settings_kwargs()), patch.dict("os.environ", {"BRAVE_API_KEY": "k"}):
            result = await supacrawl_health(client, verify_search=False)

        svc.search.assert_not_awaited()
        assert "live_probe" not in result["components"]["search"]
        assert result["status"] == "healthy"
