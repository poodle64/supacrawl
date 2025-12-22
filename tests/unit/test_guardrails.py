"""Guardrail tests to enforce test categorisation rules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Tests root directory (parent of unit/)
TESTS_ROOT = Path(__file__).parent.parent
UNIT_TESTS_DIR = TESTS_ROOT / "unit"

# Files that are explicitly allowed to import Crawl4AI (integration/e2e tests)
# These are in tests/integration/ or tests/e2e/ directories
ALLOWED_PLAYWRIGHT_IMPORTS = {
    # e2e tests (use real Crawl4AI/Playwright)
    "e2e/test_crawl4ai_quality.py",
    "e2e/test_baseline_quality.py",
    "e2e/test_preset_parity.py",
    "e2e/test_crawl_from_map.py",
    "e2e/test_manifest_metadata.py",
    "e2e/test_manifest_schema_validation.py",
    "e2e/test_output_formats_integrity.py",
    # integration tests (use mocks, no real browser)
    "integration/test_providers.py",
    "integration/test_politeness.py",
}

# Forbidden imports for unit tests
FORBIDDEN_IMPORTS = {
    "crawl4ai",
    "playwright",
}


def _get_imports(filepath: Path) -> set[str]:
    """Extract all imported module names from a Python file."""
    imports: set[str] = set()
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])

    return imports


@pytest.mark.unit
def test_unit_tests_do_not_import_crawl4ai_directly() -> None:
    """
    Verify that test files in unit/ do not import crawl4ai or playwright.
    
    Unit tests should not depend on Crawl4AI or Playwright directly.
    If a test needs these, it should be in integration/ or e2e/.
    """
    violations: list[str] = []
    unit_dir = TESTS_ROOT / "unit"

    for test_file in unit_dir.glob("test_*.py"):
        if test_file.name in ALLOWED_PLAYWRIGHT_IMPORTS:
            continue
        if test_file.name == "test_guardrails.py":
            continue

        imports = _get_imports(test_file)
        forbidden_found = imports & FORBIDDEN_IMPORTS

        if forbidden_found:
            violations.append(
                f"{test_file.name} imports {forbidden_found} but is not in allowlist"
            )

    if violations:
        msg = (
            "Unit tests should not import crawl4ai or playwright directly.\n"
            "Either:\n"
            "  1. Move the test to integration/ or e2e/ directory\n"
            "  2. Use mocks instead of real imports\n"
            "  3. Add to ALLOWED_PLAYWRIGHT_IMPORTS if truly needed\n\n"
            "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
        )
        pytest.fail(msg)


@pytest.mark.unit
def test_allowed_imports_files_exist() -> None:
    """Verify that all files in the allowlist actually exist."""
    for filepath in ALLOWED_PLAYWRIGHT_IMPORTS:
        # filepath is relative to TESTS_ROOT (e.g., "e2e/test_crawl4ai_quality.py")
        full_path = TESTS_ROOT / filepath
        if not full_path.exists():
            pytest.fail(
                f"File '{filepath}' in ALLOWED_PLAYWRIGHT_IMPORTS does not exist. "
                "Remove it from the allowlist or create the file."
            )

