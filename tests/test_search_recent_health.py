"""Health must reflect recent REAL traffic, not just a synthetic probe (#161).

The field report saw consecutive_failures: 0 while every caller was getting
nothing — because a zero-result success is counted as a failure nowhere.
SearchService now keeps a rolling window of whether recent CALLER searches came
back empty, and health degrades when the whole window is empty. The probe is
excluded (record_recent=False) so a health check never answers its own question.

The window itself is a services-layer concern and is tested there so it runs in
CI without the mcp extra; the two tests that assert the mcp health tool reacts
to it defer their ``supacrawl.mcp`` import and are marked ``mcp`` (the
test_search_quota.py convention), so a CI job without the extra deselects them
rather than crashing on collection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from supacrawl.models import SearchResultItem
from supacrawl.services.search.service import SearchService

_WINDOW = SearchService.RECENT_WINDOW


def _service() -> SearchService:
    # rate_limit high so a burst of sequential searches does not sleep the test.
    return SearchService(providers=["brave"], brave_api_key="key", rate_limit=1000)


async def _search(service: SearchService, *, empty: bool, record_recent: bool = True) -> None:
    returned = [] if empty else [SearchResultItem(url="https://x/", title="r")]
    service._chain.search = AsyncMock(return_value=returned)  # type: ignore[method-assign]
    await service.search("q", limit=3, record_recent=record_recent)


class TestRecentSearchHealth:
    @pytest.mark.asyncio
    async def test_full_window_of_empties_trips_all_recent_empty(self) -> None:
        service = _service()
        try:
            for _ in range(_WINDOW):
                await _search(service, empty=True)

            recent = service.recent_search_health
            assert recent["recent_searches"] == _WINDOW
            assert recent["recent_empty"] == _WINDOW
            assert recent["all_recent_empty"] is True
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_partial_window_is_not_all_empty(self) -> None:
        """Below a full window, the signal stays quiet — a couple of empties is
        not evidence the backend is down."""
        service = _service()
        try:
            for _ in range(_WINDOW - 1):
                await _search(service, empty=True)

            assert service.recent_search_health["all_recent_empty"] is False
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_one_result_clears_the_window(self) -> None:
        service = _service()
        try:
            for _ in range(_WINDOW):
                await _search(service, empty=True)
            assert service.recent_search_health["all_recent_empty"] is True

            await _search(service, empty=False)  # a single good result rolls in

            assert service.recent_search_health["all_recent_empty"] is False
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_probe_does_not_pollute_the_window(self) -> None:
        service = _service()
        try:
            await _search(service, empty=True)
            await _search(service, empty=True)

            # A synthetic probe: record_recent=False, so the window is untouched.
            await _search(service, empty=True, record_recent=False)

            assert service.recent_search_health["recent_searches"] == 2
        finally:
            await service.close()


@pytest.mark.mcp
class TestRecentSearchHealthConfig:
    """The mcp health tool must react to the recent-traffic signal."""

    @pytest.mark.asyncio
    async def test_health_config_degrades_when_recent_all_empty(self) -> None:
        from supacrawl.mcp.tools.health import _get_search_config

        service = _service()
        try:
            for _ in range(_WINDOW):
                await _search(service, empty=True)

            config = _get_search_config(service)

            assert config["status"] == "degraded", "health stayed ready while every recent query returned nothing"
            assert config["recent_search_health"]["all_recent_empty"] is True
            assert "all returned no results" in config["warning"]
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_health_config_stays_ready_with_recent_results(self) -> None:
        from supacrawl.mcp.tools.health import _get_search_config

        service = _service()
        try:
            for _ in range(_WINDOW):
                await _search(service, empty=False)

            config = _get_search_config(service)

            assert config["status"] == "ready"
            assert config["recent_search_health"]["all_recent_empty"] is False
        finally:
            await service.close()
