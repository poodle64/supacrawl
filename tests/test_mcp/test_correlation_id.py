"""Every MCP tool must mint a fresh correlation id per request (#161).

The correlation id is a process-wide contextvar and the server task is
long-lived, so the previous ``get_correlation_id() or generate_correlation_id()``
pattern pinned the FIRST call's id onto every later response — the same value
minutes and hours apart, correlating nothing. These tests drive the real tool
functions and assert the id varies per call, and that a stale contextvar left
by a prior call is never reused.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from api_common.correlation import set_correlation_id

pytestmark = pytest.mark.mcp

# generate_correlation_id() yields 8 lowercase hex characters.
_ID_RE = re.compile(r"^[0-9a-f]{8}$")

# The exact static value the field report saw on every search response across a
# multi-hour session — a stale contextvar left by the first call.
_STALE_ID = "8aa4943c"


async def _run_search(api_client: MagicMock) -> str:
    from supacrawl.mcp.tools.search import supacrawl_search

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    result = await supacrawl_search(api_client=api_client, ctx=ctx, query="whatever", limit=3)
    return result["correlation_id"]


class TestSearchCorrelationId:
    @pytest.mark.asyncio
    async def test_id_is_fresh_on_every_call(self, mock_api_client: MagicMock) -> None:
        first = await _run_search(mock_api_client)
        second = await _run_search(mock_api_client)
        third = await _run_search(mock_api_client)

        assert _ID_RE.match(first), f"correlation id is not the 8-char hex shape: {first!r}"
        assert len({first, second, third}) == 3, (
            f"correlation id repeated across calls (it is process-static): {[first, second, third]}"
        )

    @pytest.mark.asyncio
    async def test_stale_contextvar_is_not_reused(self, mock_api_client: MagicMock) -> None:
        """The exact defect: a prior call's id sitting in the shared contextvar."""
        set_correlation_id(_STALE_ID)

        got = await _run_search(mock_api_client)

        assert got != _STALE_ID, "the tool reused a stale correlation id read from the contextvar"
