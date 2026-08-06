"""The SearXNG credential is fetched from the secrets broker in-process (#164).

The credential must reach the server without ever being an ambient environment
variable, so ``SupacrawlServer.create_api_client`` vends it from Portcullis at
startup when ``SEARXNG_PORTCULLIS_CREDENTIAL`` names a catalogue entry.

Two properties carry the weight here and are asserted rather than assumed:

* **Unset changes nothing.** The REST API container reaches an ungated instance
  on an internal network with no credential and no broker identity at all.
* **A broker gap fails closed.** The base server treats a failed
  ``create_api_client`` as a non-fatal degraded start; what it must never do is
  continue *without* the credential, because the chain would then answer from a
  third-party engine nobody configured — the very thing this path prevents.

The broker is mocked throughout: no live broker, and no realistic-looking
credential anywhere in this file.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_common.exceptions import MCPConnectionError

from supacrawl.mcp.config import SupacrawlSettings
from supacrawl.mcp.exceptions import SupacrawlConnectionError
from supacrawl.mcp.server import SupacrawlServer

pytestmark = pytest.mark.mcp

CREDENTIAL_NAME = "searxng-credential-name-placeholder"

# Obvious placeholders — never a real credential (rules-library core/21-secret-handling.md).
VENDED_USERNAME = "vended-user-placeholder"
VENDED_PASSWORD = "vended-password-placeholder"

# Vocabulary rule 17 (mcp-servers 17-portcullis-consumer-boundary.md) forbids in a
# consumer's broker-gap message: a remedy, an operator action, a broker CLI verb,
# a vault path, or auth-flow mechanics.
FORBIDDEN_IN_A_GAP_MESSAGE = (
    "unlock",
    "restart",
    "mint",
    "vault",
    "bitwarden",
    "attest",
    "bearer",
    "token",
    "key file",
    "portcullis unlock",
)


def _server(credential_name: str) -> SupacrawlServer:
    """A server whose only non-default setting is the credential name."""
    return SupacrawlServer(settings=SupacrawlSettings(SEARXNG_PORTCULLIS_CREDENTIAL=credential_name))


class TestUnsetCredentialChangesNothing:
    """The default must be byte-for-byte the behaviour that shipped before."""

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
    async def test_services_are_built_with_no_supplied_credential(self) -> None:
        """None, not an empty string: the provider must fall through to the env."""
        server = _server("")
        create = AsyncMock(return_value=MagicMock())

        with (
            patch.object(server, "vend_static_fields", AsyncMock()),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
        ):
            await server.create_api_client()

        assert create.call_args.kwargs == {"searxng_username": None, "searxng_password": None}


class TestVendedCredentialReachesTheServices:
    @pytest.mark.asyncio
    async def test_vended_pair_is_forwarded(self) -> None:
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())
        vend = AsyncMock(return_value={"username": VENDED_USERNAME, "password": VENDED_PASSWORD})

        with (
            patch.object(server, "vend_static_fields", vend),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
        ):
            await server.create_api_client()

        assert create.call_args.kwargs == {
            "searxng_username": VENDED_USERNAME,
            "searxng_password": VENDED_PASSWORD,
        }

    @pytest.mark.asyncio
    async def test_the_configured_name_is_what_is_vended(self) -> None:
        server = _server(CREDENTIAL_NAME)
        vend = AsyncMock(return_value={"username": VENDED_USERNAME, "password": VENDED_PASSWORD})

        with (
            patch.object(server, "vend_static_fields", vend),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
        ):
            await server.create_api_client()

        assert vend.call_args.args == (CREDENTIAL_NAME,)
        # The gap error must name the credential family, not the consumer: the
        # server-wide label would read "supacrawl", which says nothing about what
        # could not be produced.
        assert vend.call_args.kwargs == {"vendor": "searxng"}

    @pytest.mark.asyncio
    async def test_the_credential_value_is_never_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        server = _server(CREDENTIAL_NAME)
        vend = AsyncMock(return_value={"username": VENDED_USERNAME, "password": VENDED_PASSWORD})

        import logging

        with (
            caplog.at_level(logging.DEBUG),
            patch.object(server, "vend_static_fields", vend),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
        ):
            await server.create_api_client()

        assert VENDED_PASSWORD not in caplog.text
        assert VENDED_USERNAME not in caplog.text


class TestBrokerGapFailsClosed:
    """A gap must degrade the server, never quietly find another engine."""

    @pytest.mark.asyncio
    async def test_broker_failure_propagates_and_builds_nothing(self) -> None:
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())
        gap = SupacrawlConnectionError(
            "Portcullis did not return a usable searxng session.",
            context={"dependency": "portcullis", "vendor": "searxng", "gap": "no_session"},
        )

        with (
            patch.object(server, "vend_static_fields", AsyncMock(side_effect=gap)),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
            pytest.raises(SupacrawlConnectionError),
        ):
            await server.create_api_client()

        # Nothing was constructed, so no provider chain exists to fall through to
        # DuckDuckGo or any other third-party engine.
        create.assert_not_called()

    @pytest.mark.asyncio
    async def test_half_a_vended_pair_is_refused(self) -> None:
        """A username with no password cannot authenticate.

        Letting it through would look like a working vend right up to the 401,
        and under a strict provider chain that 401 is indistinguishable from an
        instance being down.
        """
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())

        for fields in ({"username": VENDED_USERNAME}, {"password": VENDED_PASSWORD}, {}):
            with (
                patch.object(server, "vend_static_fields", AsyncMock(return_value=fields)),
                patch("supacrawl.mcp.server.create_supacrawl_services", create),
                pytest.raises(SupacrawlConnectionError) as excinfo,
            ):
                await server.create_api_client()

            assert excinfo.value.context["gap"] == "no_session"

        create.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_empty_vended_value_is_refused(self) -> None:
        """A present-but-blank field is the same non-credential as a missing one."""
        server = _server(CREDENTIAL_NAME)
        create = AsyncMock(return_value=MagicMock())

        with (
            patch.object(server, "vend_static_fields", AsyncMock(return_value={"username": "", "password": ""})),
            patch("supacrawl.mcp.server.create_supacrawl_services", create),
            pytest.raises(SupacrawlConnectionError),
        ):
            await server.create_api_client()

        create.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_failure_reaches_the_base_initialise_sequence(self) -> None:
        """Proves the degrade is real, not just an exception in isolation.

        ``run_async_server`` starts the server degraded when this sequence
        raises. The value asserted here is that nothing between
        ``create_api_client`` and that branch swallows the gap and leaves a
        half-built client behind.
        """
        server = _server(CREDENTIAL_NAME)
        gap = SupacrawlConnectionError("Portcullis did not return a usable searxng session.")

        with (
            patch.object(server, "vend_static_fields", AsyncMock(side_effect=gap)),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
            pytest.raises(SupacrawlConnectionError),
        ):
            await server.initialize_client()

        assert server.api_client is None


class TestConsumerBoundaryContract:
    """Rule 17 (mcp-servers ``17-portcullis-consumer-boundary.md``)."""

    def test_the_typed_error_is_declared_and_on_the_right_lineage(self) -> None:
        assert SupacrawlServer.portcullis_connection_error_cls is SupacrawlConnectionError
        assert issubclass(SupacrawlConnectionError, MCPConnectionError)

    def test_the_typed_error_is_not_a_retryable_builtin(self) -> None:
        """FastMCP's RetryMiddleware retries builtin ConnectionError/TimeoutError.

        A broker outage will not recover inside its retry window, so the gap must
        surface as a type the middleware treats as non-retryable.
        """
        assert not issubclass(SupacrawlConnectionError, ConnectionError)
        assert not issubclass(SupacrawlConnectionError, TimeoutError)

    @pytest.mark.asyncio
    async def test_the_gap_message_names_only_the_gap(self) -> None:
        server = _server(CREDENTIAL_NAME)

        with (
            patch.object(server, "vend_static_fields", AsyncMock(return_value={"username": VENDED_USERNAME})),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
            pytest.raises(SupacrawlConnectionError) as excinfo,
        ):
            await server.create_api_client()

        message = str(excinfo.value).lower()
        assert "portcullis did not return a usable searxng session" in message
        for forbidden in FORBIDDEN_IN_A_GAP_MESSAGE:
            assert forbidden not in message, f"the gap message prescribes or discloses {forbidden!r}"

    @pytest.mark.asyncio
    async def test_no_credential_material_appears_in_the_gap_error(self) -> None:
        """A partial vend must not echo back the half it did receive."""
        server = _server(CREDENTIAL_NAME)

        with (
            patch.object(server, "vend_static_fields", AsyncMock(return_value={"username": VENDED_USERNAME})),
            patch("supacrawl.mcp.server.create_supacrawl_services", AsyncMock(return_value=MagicMock())),
            pytest.raises(SupacrawlConnectionError) as excinfo,
        ):
            await server.create_api_client()

        rendered = f"{excinfo.value!s} {excinfo.value!r} {excinfo.value.context}"
        assert VENDED_USERNAME not in rendered
        assert VENDED_PASSWORD not in rendered
