"""
Configuration validation utilities for MCP servers.

Provides Pydantic field validators for common configuration patterns.

Usage:
    >>> from .config import validate_base_url, parse_comma_separated
    >>> validate_base_url("https://api.example.com")
    'https://api.example.com'
    >>> parse_comma_separated("a, b, c")
    ['a', 'b', 'c']
"""

import json
from typing import Any
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
)


class LenientEnvSettingsSource(EnvSettingsSource):
    """EnvSettingsSource that tolerates comma-separated strings for list fields.

    pydantic-settings 2.12 calls ``decode_complex_value`` (a JSON decode) on
    env values for "complex" field types (``list[str]``, ``dict``, ...) *before*
    any ``field_validator(mode="before")`` runs. A comma-separated value like
    ``/srv/a,/srv/b`` is not valid JSON, so the decode raises ``JSONDecodeError``
    and the whole Settings construction fails at import time -- the server will
    not start.

    This source catches that decode failure and returns the raw string, letting
    the field's ``mode="before"`` validator (typically ``parse_comma_separated``)
    perform the split. A genuine JSON array value (``["a","b"]``) still decodes
    normally, so both env-var formats are accepted.
    """

    def decode_complex_value(self, field_name: str, field_info: Any, value: Any) -> Any:
        """JSON-decode as usual; fall back to the raw string on decode failure."""
        try:
            return super().decode_complex_value(field_name, field_info, value)
        except json.JSONDecodeError, ValueError:
            return value


class LenientDotEnvSettingsSource(LenientEnvSettingsSource, DotEnvSettingsSource):
    """``DotEnvSettingsSource`` with the same comma-toleration as the env source.

    Applies the lenient decode to values loaded from a ``.env`` file as well as
    from the process environment, so the two surfaces behave identically.
    """


def lenient_env_settings_sources(
    settings_cls: type[BaseSettings],
    init_settings: PydanticBaseSettingsSource,
    file_secret_settings: PydanticBaseSettingsSource,
) -> tuple[PydanticBaseSettingsSource, ...]:
    """Build the standard source tuple with lenient env/dotenv sources.

    Settings classes that declare ``list[str]`` fields populated from
    comma-separated environment variables must override
    ``settings_customise_sources`` to delegate here, otherwise pydantic-settings
    2.12 crashes on the eager JSON decode (see ``LenientEnvSettingsSource``).

    Args:
        settings_cls: The ``BaseSettings`` subclass being constructed; pass the
            ``settings_cls`` argument received by ``settings_customise_sources``.
        init_settings: The init-source passed to ``settings_customise_sources``.
        file_secret_settings: The file-secret source passed to
            ``settings_customise_sources``.

    Returns:
        A source tuple in the standard precedence order (init > env > dotenv >
        file secrets), with the env and dotenv sources replaced by their lenient
        variants.

    Examples:
        >>> from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
        >>> class MySettings(BaseSettings):
        ...     @classmethod
        ...     def settings_customise_sources(
        ...         cls, settings_cls, init_settings, env_settings,
        ...         dotenv_settings, file_secret_settings,
        ...     ):
        ...         return lenient_env_settings_sources(
        ...             settings_cls, init_settings, file_secret_settings
        ...         )
    """
    return (
        init_settings,
        LenientEnvSettingsSource(settings_cls),
        LenientDotEnvSettingsSource(settings_cls),
        file_secret_settings,
    )


class BaseMCPSettings(BaseSettings):
    """Base ``BaseSettings`` for every MCP server's settings class.

    Carries the household-wide settings behaviour that would otherwise be
    copy-pasted into each server's config module. Currently that is the lenient
    env-source wiring (see ``LenientEnvSettingsSource``), which lets any
    ``list[str]`` field accept a comma-separated env var without crashing under
    pydantic-settings 2.12's eager JSON decode.

    Servers subclass this instead of ``pydantic_settings.BaseSettings`` and set
    their own ``model_config`` (``env_prefix``, ``env_file``, ...) plus their
    own fields and validators as usual; pydantic merges the child
    ``model_config`` over the base and inherits this source override.

    Example:
        >>> from pydantic import Field
        >>> from pydantic_settings import SettingsConfigDict
        >>> class FooSettings(BaseMCPSettings):
        ...     model_config = SettingsConfigDict(env_prefix="FOO_", extra="ignore")
        ...     allowed_origins: list[str] = Field(
        ...         default_factory=lambda: ["*"], alias="ALLOWED_ORIGINS"
        ...     )
    """

    portcullis_url: str = Field(default="http://localhost:8311", alias="PORTCULLIS_URL")
    signet_identity: str = Field(default="", alias="SIGNET_IDENTITY")
    signet_slot: str = Field(default="", alias="SIGNET_SLOT")
    signet_backend: str = Field(default="", alias="SIGNET_BACKEND")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Install the lenient env/dotenv sources for all subclasses."""
        return lenient_env_settings_sources(settings_cls, init_settings, file_secret_settings)


def parse_comma_separated(v: str | list[str]) -> list[str]:
    """
    Parse comma-separated string into list.

    Common validator for ALLOWED_ORIGINS, ALLOWED_HOSTS, and similar fields.
    Can be used as a Pydantic field_validator with mode="before".

    Args:
        v: Either a comma-separated string or already a list of strings

    Returns:
        List of trimmed strings

    Examples:
        >>> parse_comma_separated("http://localhost,http://example.com")
        ['http://localhost', 'http://example.com']

        >>> parse_comma_separated(["a", "b"])
        ['a', 'b']

        >>> parse_comma_separated("  spaced , values  ")
        ['spaced', 'values']
    """
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


def validate_base_url(
    v: str,
    field_name: str = "base_url",
    strip_trailing_slash: bool = False,
) -> str:
    """
    Validate base URL format - reusable across all MCP servers.

    Validates:
    - URL is not empty
    - URL has valid format (scheme and netloc)
    - URL scheme is http or https

    Args:
        v: The URL value to validate
        field_name: Name of the field for error messages (default: "base_url")
        strip_trailing_slash: If True, strip trailing slash from URL (default: False)

    Returns:
        Validated URL (with trailing slash stripped if requested)

    Raises:
        ValueError: If URL is invalid

    Examples:
        >>> validate_base_url("https://api.example.com")
        'https://api.example.com'

        >>> validate_base_url("https://api.example.com/", strip_trailing_slash=True)
        'https://api.example.com'
    """
    if not v:
        raise ValueError(f"{field_name.upper()} cannot be empty")

    try:
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL format: {v}")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL scheme must be http or https: {v}")
    except Exception as e:
        if isinstance(e, ValueError) and (
            "cannot be empty" in str(e) or "Invalid URL" in str(e) or "scheme must be" in str(e)
        ):
            raise
        raise ValueError(f"Invalid {field_name} format: {e}") from e

    return v.rstrip("/") if strip_trailing_slash else v
