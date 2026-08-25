"""The Loki push token is fetched from the secrets broker in-process at startup.

The MCP server is the long-running entry point that ships field telemetry to the
household Loki. The bearer that authenticates those pushes must reach the server
without ever being an ambient environment variable, so
``SupacrawlServer.create_api_client`` vends it from Portcullis at startup when
``SUPACRAWL_METRICS_PORTCULLIS_CREDENTIAL`` names a catalogue entry (defaulting
to ``loki-push``).

Two properties carry the weight here and are asserted rather than assumed:

* **Unset changes nothing.** Empty the credential name and the sink resolves the
  bearer from ``SUPACRAWL_METRICS_TOKEN`` exactly as before — the env var is the
  unset-case fallback, never a second source alongside the broker.
* **A broker gap degrades, it does not fail closed.** Unlike the SearXNG
  credential (a missing search credential fails search loudly), telemetry is
  best-effort: a broker gap — the vault re-locks within ~15–35 minutes of an
  unlock (``portcullis#178``) — disables remote metrics with a WARNING and the
  server keeps serving. There is deliberately NO env fallback on a vend failure,
  because that env token is the stale path this move replaced.

The broker is mocked throughout: no live broker, and no realistic-looking
credential anywhere in this file.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from supacrawl.mcp.config import SupacrawlSettings
from supacrawl.mcp.exceptions import SupacrawlConnectionError
from supacrawl.mcp.server import SupacrawlServer

pytestmark = pytest.mark.mcp

# A placeholder credential NAME (an identifier, never a value). The default the
# field ships with is "loki-push"; tests use an explicit name to be unambiguous
# about what they exercise.
CREDENTIAL_NAME = "loki-push-credential-name-placeholder"

# Obvious placeholders — never a real credential (rules-library core/21-secret-handling.md).
VENDED_TOKEN = "vended-loki-token-placeholder"


def _server(credential_name: str) -> SupacrawlServer:
    """A server whose only non-default setting is the metrics credential name."""
    return SupacrawlServer(settings=SupacrawlSettings(metrics_portcullis_credential=credential_name))


class TestUnsetCredentialChangesNothing:
    """Empty credential name = the env path, byte-for-byte as it shipped."""

    @pytest.mark.asyncio
    async def test_no_vend_is_attempted(self) -> None:
        server = _server("")
        vend = AsyncMock()

        with (
            patch.object(server, "vend_static_fields", vend),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
        ):
            await server.create_api_client()

        vend.assert_not_called()

    @pytest.mark.asyncio
    async def test_services_are_built_with_no_vended_token(self) -> None:
        """vended=False, metrics_token=None: the sink must fall through to the env."""
        server = _server("")
        create = AsyncMock(return_value=MagicMock())

        with (
            patch.object(server, "vend_static_fields", AsyncMock()),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
        ):
            await server.create_api_client()

        assert create.call_args.kwargs["metrics_token"] is None
        assert create.call_args.kwargs["metrics_token_vended"] is False


class TestVendedTokenReachesTheServices:
    @pytest.mark.asyncio
    async def test_vended_token_is_forwarded(self) -> None:
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())
        vend = AsyncMock(return_value={"value": VENDED_TOKEN})

        with (
            patch.object(server, "vend_static_fields", vend),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
        ):
            await server.create_api_client()

        assert create.call_args.kwargs["metrics_token"] == VENDED_TOKEN
        assert create.call_args.kwargs["metrics_token_vended"] is True

    @pytest.mark.asyncio
    async def test_the_configured_name_is_what_is_vended(self) -> None:
        server = _server(CREDENTIAL_NAME)
        vend = AsyncMock(return_value={"value": VENDED_TOKEN})

        with (
            patch.object(server, "vend_static_fields", vend),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
        ):
            await server.create_api_client()

        assert vend.call_args.args == (CREDENTIAL_NAME,)
        # The vendor label names the credential family, not the consumer.
        assert vend.call_args.kwargs == {"vendor": "loki-push"}

    @pytest.mark.asyncio
    async def test_the_token_value_is_never_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        server = _server(CREDENTIAL_NAME)
        vend = AsyncMock(return_value={"value": VENDED_TOKEN})

        import logging

        with (
            caplog.at_level(logging.DEBUG),
            patch.object(server, "vend_static_fields", vend),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
        ):
            await server.create_api_client()

        assert VENDED_TOKEN not in caplog.text


class TestBrokerGapDegrades:
    """A gap must disable remote metrics, never break a scrape or refuse to start.

    The deliberate divergence from the SearXNG credential: search fails closed
    (a missing credential degrades search loudly rather than handing the query
    to an unconfigured engine); telemetry fails open (best-effort by design, the
    remote sink is fail-open, and the local JSONL is the source of truth).
    """

    @pytest.mark.asyncio
    async def test_broker_failure_is_swallowed_and_services_still_build(self, caplog: pytest.LogCaptureFixture) -> None:
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())
        gap = SupacrawlConnectionError(
            "Portcullis did not return a usable loki-push session.",
            context={"dependency": "portcullis", "vendor": "loki-push", "gap": "no_session"},
        )

        import logging

        with (
            caplog.at_level(logging.WARNING),
            patch.object(server, "vend_static_fields", AsyncMock(side_effect=gap)),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
        ):
            # Must NOT raise — the server keeps serving.
            await server.create_api_client()

        # Services were still built (scrapes/searches are unaffected), but with
        # vended=True and a None token: the broker path is authoritative, so the
        # sink does NOT fall back to the (stale) env token.
        assert create.call_args.kwargs["metrics_token"] is None
        assert create.call_args.kwargs["metrics_token_vended"] is True
        assert "could not be resolved from Portcullis" in caplog.text
        # No credential material in the log.
        assert VENDED_TOKEN not in caplog.text

    @pytest.mark.asyncio
    async def test_an_empty_vended_token_degrades_without_raising(self) -> None:
        """A present-but-blank token is the same non-credential as a missing one."""
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())

        with (
            patch.object(server, "vend_static_fields", AsyncMock(return_value={"value": ""})),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
        ):
            await server.create_api_client()

        assert create.call_args.kwargs["metrics_token"] is None
        assert create.call_args.kwargs["metrics_token_vended"] is True

    @pytest.mark.asyncio
    async def test_a_missing_value_field_degrades_without_raising(self) -> None:
        """A credential with no `value` field cannot authenticate — degrade."""
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())

        with (
            patch.object(server, "vend_static_fields", AsyncMock(return_value={"token": "wrong-field"})),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
        ):
            await server.create_api_client()

        assert create.call_args.kwargs["metrics_token"] is None
        assert create.call_args.kwargs["metrics_token_vended"] is True

    @pytest.mark.asyncio
    async def test_the_failure_does_not_take_the_server_down(self) -> None:
        """Proves the degrade is real, not just an exception in isolation.

        ``initialize_client`` runs the full startup sequence; a metrics-vend gap
        must leave it intact (the SearXNG gap degrades the server, the metrics gap
        must not even do that — the server serves everything, just no remote push).
        """
        server = _server(CREDENTIAL_NAME)
        gap = SupacrawlConnectionError("Portcullis did not return a usable loki-push session.")

        with (
            patch.object(server, "vend_static_fields", AsyncMock(side_effect=gap)),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
        ):
            await server.initialize_client()

        # The client was built despite the gap — the server is up and serving.
        assert server.api_client is not None


class TestConsumerBoundaryContract:
    """The metrics vend reuses the SearXNG vend's typed-error lineage (rule 17)."""

    def test_the_typed_error_is_the_same_lineage(self) -> None:
        assert SupacrawlServer.portcullis_connection_error_cls is SupacrawlConnectionError

    @pytest.mark.asyncio
    async def test_no_credential_material_appears_in_the_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """A degraded vend must log the gap without echoing any token it saw."""
        server = _server(CREDENTIAL_NAME)

        import logging

        with (
            caplog.at_level(logging.WARNING),
            patch.object(server, "vend_static_fields", AsyncMock(return_value={"value": VENDED_TOKEN})),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
        ):
            await server.create_api_client()

        assert VENDED_TOKEN not in caplog.text
