"""Validation tests for data models."""

from __future__ import annotations

import pytest

from supacrawl.exceptions import ValidationError
from supacrawl.models import SiteConfig


def base_config() -> dict[str, object]:
    """Return a valid config payload for mutation in tests."""
    return {
        "id": "example",
        "name": "Example",
        "entrypoints": ["https://example.com"],
        "include": ["https://example.com"],
        "exclude": [],
        "max_pages": 5,
        "formats": ["markdown"],
        "only_main_content": True,
        "include_subdomains": False,
    }


def test_entrypoints_validation_requires_at_least_one() -> None:
    """Empty entrypoints should raise validation error with correlation ID."""
    payload = base_config()
    payload["entrypoints"] = []

    with pytest.raises(ValidationError) as exc_info:
        SiteConfig(**payload)

    message = str(exc_info.value)
    assert "entrypoint" in message
    assert "correlation_id=" in message


def test_max_pages_must_be_positive() -> None:
    """Zero or negative max_pages should raise validation error."""
    payload = base_config()
    payload["max_pages"] = 0

    with pytest.raises(ValidationError) as exc_info:
        SiteConfig(**payload)

    message = str(exc_info.value)
    assert "max_pages" in message
    assert "correlation_id=" in message


def test_max_pages_negative_raises() -> None:
    """Negative max_pages should raise validation error."""
    payload = base_config()
    payload["max_pages"] = -1

    with pytest.raises(ValidationError) as exc_info:
        SiteConfig(**payload)

    message = str(exc_info.value)
    assert "max_pages" in message
    assert "correlation_id=" in message


def test_entrypoints_invalid_url_format() -> None:
    """Invalid URL format in entrypoints should be accepted (validation happens at provider level)."""
    payload = base_config()
    payload["entrypoints"] = ["not-a-url"]

    config = SiteConfig(**payload)
    assert config.entrypoints == ["not-a-url"]


def test_formats_empty_list_defaults_to_markdown() -> None:
    """Empty formats list should default to markdown."""
    payload = base_config()
    payload["formats"] = []

    config = SiteConfig(**payload)
    assert config.formats == ["markdown"]


def test_boolean_fields_normalize_strings() -> None:
    """Boolean fields should normalize string values (Pydantic converts 'true'/'false' to booleans)."""
    payload = base_config()
    payload["only_main_content"] = "true"

    config = SiteConfig(**payload)
    assert config.only_main_content is True
    assert isinstance(config.only_main_content, bool)
