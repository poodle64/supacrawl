"""Pytest configuration and shared fixtures for supacrawl tests."""

import os
from pathlib import Path

import pytest

# Keep per-domain strategy memory (#130) and field telemetry (#137) off by default
# in tests so a test that drives the CLI/MCP scrape path cannot write to the
# developer's real ~/.supacrawl/. Tests that exercise them pass an explicit
# store / sink with a tmp dir, which bypasses these env defaults.
os.environ.setdefault("SUPACRAWL_STRATEGY_MEMORY", "0")
os.environ.setdefault("SUPACRAWL_METRICS", "0")

# Search-related env vars that a developer's direnv cascade (source_up) may inject
# into the test process.  Each search test class that tests default/keyless behaviour
# must run against a clean slate so assertions about "no key configured" hold
# regardless of what the ambient environment has set.
_SEARCH_ENV_VARS = (
    "BRAVE_API_KEY",
    "SERPER_API_KEY",
    "SERPAPI_API_KEY",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "SEARXNG_URL",
    "SUPACRAWL_SEARCH_PROVIDERS",
    "SUPACRAWL_LOCALE",
    "SUPACRAWL_SEARCH_RATE_LIMIT",
)

from supacrawl.benchmark.models import CaseMetrics, CaseResult  # noqa: E402


@pytest.fixture(autouse=True)
def clean_search_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove search-related env vars that a direnv cascade may inject.

    Tests that assert default/keyless search behaviour must run against a clean
    environment, not the developer's real credentials.  Tests that need a specific
    env var set it themselves via ``monkeypatch.setenv`` or ``patch.dict``, which
    compose correctly with this fixture.
    """
    for var in _SEARCH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def make_case_result(
    case_id: str,
    *,
    quality: float | None = 80.0,
    success: bool = True,
    scored: bool = True,
    category: str = "static",
    latency_ms: float = 123.0,
    markdown_chars: int = 500,
    markdown_words: int = 100,
) -> CaseResult:
    """Build a synthetic CaseResult for benchmark tests.

    The defaults match the original ``_make_case_result`` helper in
    ``test_benchmark_store.py``.  Call sites that previously relied on the
    leaner ``_make_case`` helper in ``test_benchmark_runner.py`` (which used
    ``latency_ms=100.0`` and omitted ``markdown_chars``/``markdown_words``)
    must pass those values explicitly so that effective test inputs are
    unchanged.

    Args:
        case_id: Stable case identifier.
        quality: Composite quality score or None.
        success: Whether the scrape succeeded.
        scored: Whether the case contributes to the aggregate.
        category: Case category string.
        latency_ms: Simulated scrape latency in milliseconds.
        markdown_chars: Character count stored in the metrics.
        markdown_words: Word count stored in the metrics.

    Returns:
        A ``CaseResult`` populated with the requested data.
    """
    return CaseResult(
        case_id=case_id,
        category=category,
        url=f"https://example.com/{case_id}",
        difficulty=2,
        scored=scored,
        metrics=CaseMetrics(
            success=success,
            quality=quality,
            latency_ms=latency_ms,
            markdown_chars=markdown_chars,
            markdown_words=markdown_words,
        ),
    )


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
