"""Tests for site configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from web_scraper.exceptions import FileNotFoundError
from web_scraper.sites.loader import list_site_configs, load_site_config


def test_list_site_configs_returns_sorted_paths(tmp_path: Path) -> None:
    """List site configs returns sorted YAML file paths."""
    first = tmp_path / "b.yaml"
    second = tmp_path / "a.yaml"
    first.write_text(
        "id: b\nname: B\nentrypoints: []\ninclude: []\nexclude: []\nmax_pages: 1\nformats: []\nonly_main_content: true\ninclude_subdomains: false\n",
        encoding="utf-8",
    )
    second.write_text(
        "id: a\nname: A\nentrypoints: []\ninclude: []\nexclude: []\nmax_pages: 1\nformats: []\nonly_main_content: true\ninclude_subdomains: false\n",
        encoding="utf-8",
    )

    configs = list_site_configs(tmp_path)

    assert [path.name for path in configs] == ["a.yaml", "b.yaml"]


def test_load_site_config_parses_yaml(tmp_path: Path) -> None:
    """Load site config parses YAML into SiteConfig."""
    config_path = tmp_path / "example.yaml"
    config_path.write_text(
        "id: example\n"
        "name: Example\n"
        "entrypoints:\n"
        "  - https://example.com\n"
        "include: []\n"
        "exclude: []\n"
        "max_pages: 5\n"
        "formats:\n"
        "  - markdown\n"
        "only_main_content: true\n"
        "include_subdomains: false\n",
        encoding="utf-8",
    )

    config = load_site_config("example", tmp_path)

    assert config.id == "example"
    assert config.entrypoints == ["https://example.com"]
    assert config.max_pages == 5


def test_load_site_config_missing_file_raises(tmp_path: Path) -> None:
    """Load site config raises when file is missing."""
    with pytest.raises(FileNotFoundError):
        load_site_config("missing", tmp_path)


def test_load_site_config_empty_file_raises_configuration_error(tmp_path: Path) -> None:
    """Empty YAML results in a configuration error with correlation ID."""
    config_path = tmp_path / "empty.yaml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(Exception) as exc_info:
        load_site_config("empty", tmp_path)

    message = str(exc_info.value)
    assert "Site configuration is empty" in message
    assert "correlation_id=" in message


def test_load_site_config_malformed_yaml_raises_configuration_error(
    tmp_path: Path,
) -> None:
    """Malformed YAML surfaces as a configuration error with context."""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("id: bad: malformed", encoding="utf-8")

    with pytest.raises(Exception):
        load_site_config("bad", tmp_path)
