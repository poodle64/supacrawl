"""Pytest configuration and shared fixtures for supacrawl tests."""

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Pure logic tests with no I/O, network, or browser")
    config.addinivalue_line("markers", "integration: Filesystem-heavy tests, may use local HTTP server and Playwright")
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests with live network, Playwright, or external services",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Apply default markers to tests without explicit markers.

    Tests should use explicit markers (@pytest.mark.unit, @pytest.mark.e2e).
    Unmarked tests default to unit.
    """
    for item in items:
        # Skip if already has a category marker
        markers = list(item.iter_markers())
        marker_names = [m.name for m in markers]
        if any(m in marker_names for m in ("unit", "integration", "e2e")):
            continue

        # Default unmarked tests to unit
        item.add_marker(pytest.mark.unit)


# E2E test fixtures


@pytest.fixture
def test_urls() -> list[str]:
    """Common test URLs for E2E tests."""
    return [
        "https://example.com",
        "https://example.org",
    ]


@pytest.fixture
def urls_file(tmp_path: Path, test_urls: list[str]) -> Path:
    """Create temporary URLs file for E2E tests.

    Args:
        tmp_path: Pytest temporary directory.
        test_urls: List of test URLs.

    Returns:
        Path to created URLs file.
    """
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("\n".join(test_urls), encoding="utf-8")
    return urls_file
