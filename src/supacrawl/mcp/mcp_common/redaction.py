"""Response-time secret redaction for MCP server payloads.

This module redacts secret-bearing fields from response payloads BEFORE
they reach the LLM context. The principle is "mask by default, opt-in to
reveal": routine read calls return a length-preserving sentinel in place
of secret values, and the caller must explicitly request the raw value.

The redactor preserves the schema shape; only the value is replaced. The
sentinel is `<redacted, N chars>` so the agent can confirm the field
exists and roughly how long the secret is (useful for sanity-checking
that a rotation actually changed it).

Servers compose a domain-specific allow-list of field names by extending
DEFAULT_SECRET_KEYS.

Usage:
    >>> from .redaction import redact_secrets, DEFAULT_SECRET_KEYS
    >>> UNIFI_SECRET_KEYS = DEFAULT_SECRET_KEYS | {"x_passphrase"}
    >>> redact_secrets({"name": "iot", "x_passphrase": "hunter2"}, UNIFI_SECRET_KEYS)
    {'name': 'iot', 'x_passphrase': '<redacted, 7 chars>'}
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

DEFAULT_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "auth_token",
        "authorization",
        "bearer",
        "credential",
        "credentials",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "token",
    }
)


def _sentinel(value: Any) -> str:
    """Build the redaction sentinel for a value, preserving its length."""
    if value is None:
        return "<redacted, null>"
    if isinstance(value, str):
        return f"<redacted, {len(value)} chars>"
    if isinstance(value, (bytes, bytearray)):
        return f"<redacted, {len(value)} bytes>"
    return f"<redacted, {type(value).__name__}>"


def _matches(key: str, secret_keys: frozenset[str]) -> bool:
    """Match a key against the allow-list, normalising case and dashes."""
    normalised = key.lower().replace("-", "_")
    return normalised in secret_keys


def redact_secrets(
    data: Any,
    secret_keys: frozenset[str] = DEFAULT_SECRET_KEYS,
) -> Any:
    """Redact secret-bearing fields from a response payload in-depth.

    Walks dicts and lists recursively. When a key matches the allow-list,
    its value is replaced with a length-preserving sentinel string. Other
    fields and structure are unchanged.

    Args:
        data: The response payload (dict, list, or scalar).
        secret_keys: Frozen set of field names whose values must be
            redacted. Matching is case-insensitive and dash/underscore
            equivalent. Defaults to DEFAULT_SECRET_KEYS.

    Returns:
        A new structure with secret values replaced. Non-mapping inputs
        pass through unchanged because the unit of redaction is a key.

    Notes:
        Returns a new structure rather than mutating the input so the
        caller can keep the raw payload available (e.g. for the
        reveal_secrets=True opt-in path).
    """
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and _matches(key, secret_keys):
                result[key] = _sentinel(value)
            else:
                result[key] = redact_secrets(value, secret_keys)
        return result
    if isinstance(data, list):
        return [redact_secrets(item, secret_keys) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_secrets(item, secret_keys) for item in data)
    return data


def make_masker(
    extra_keys: Iterable[str] = (),
) -> Callable[[Any, bool], Any]:
    """Build a server-specific `mask_secrets(payload, reveal)` helper.

    Each MCP server needs the same three-line wrapper that binds its
    domain-specific allow-list to the redactor and honours a
    `reveal_secrets=True` opt-in. This factory builds that wrapper so
    callers can write::

        mask_secrets = make_masker({"x_passphrase", "x_authkey"})
        ...
        return mask_secrets(payload, reveal=reveal_secrets)

    The returned callable accepts `reveal` as a keyword to keep call
    sites self-documenting at the tool boundary.

    Args:
        extra_keys: Server-specific field names to add to
            DEFAULT_SECRET_KEYS. Matched case-insensitively with
            dash/underscore equivalence.

    Returns:
        A masker bound to the union of DEFAULT_SECRET_KEYS and
        extra_keys. Returns the input unchanged when reveal is True.
    """
    secret_keys = DEFAULT_SECRET_KEYS | frozenset(extra_keys)

    def mask(payload: Any, reveal: bool = False) -> Any:
        if reveal:
            return payload
        return redact_secrets(payload, secret_keys)

    return mask
