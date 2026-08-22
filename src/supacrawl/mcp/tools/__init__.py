"""Supacrawl MCP tool package, and the server's secret-redaction binding.

mcp-servers rule 70 §'Allow-list and helper' asks every server to bind
``mask_secrets = make_masker({SERVICE}_SECRET_KEYS)`` at module level here, so
a credential-shaped key can never leave in a response envelope. Supacrawl
never carried the binding: the fleet's redaction gate could not see an
embedded server's package at all, so the omission read as compliance for as
long as a ``.redaction-exempt`` dotfile sat beside the container shell in
mcp-servers.

The allow-list carries supacrawl's own extras; ``make_masker`` unions
``mcp_common.redaction.DEFAULT_SECRET_KEYS`` internally, so the generic names
(``api_key``, ``token``, ``password`` ...) are not restated here.
"""

from mcp_common.redaction import make_masker

#: Credential-bearing field names specific to supacrawl's configuration
#: surface. ``proxy`` is in because a proxy URL routinely embeds
#: ``user:pass@`` -- it is a credential wearing a URL's clothes. The
#: ``*_portcullis_credential`` fields are NOT in: they name a vault item, they
#: do not carry its value, and masking them would hide which credential a
#: degraded health report is complaining about.
SUPACRAWL_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "captcha_api_key",
        "mcp_auth_token",
        "metrics_token",
        "proxy",
        "searxng_password",
    }
)

mask_secrets = make_masker(SUPACRAWL_SECRET_KEYS)
