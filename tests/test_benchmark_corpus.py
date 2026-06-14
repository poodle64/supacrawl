"""Unit tests for benchmark/corpus.py.

Verifies that the default corpus loads cleanly, IDs are unique, is_scored
reflects stable/scored, and every case has a non-empty why field.
"""

from __future__ import annotations

import pytest

from supacrawl.benchmark.corpus import load_default_suite
from supacrawl.benchmark.models import BenchSuite


@pytest.mark.unit
def test_default_suite_loads() -> None:
    suite = load_default_suite()
    assert isinstance(suite, BenchSuite)
    assert suite.name == "default"
    assert len(suite.cases) > 0


@pytest.mark.unit
def test_default_suite_has_cases() -> None:
    suite = load_default_suite()
    # Expect at least the 17 curated cases
    assert len(suite.cases) >= 17


@pytest.mark.unit
def test_case_ids_are_unique() -> None:
    suite = load_default_suite()
    ids = [c.id for c in suite.cases]
    assert len(ids) == len(set(ids)), "Duplicate case IDs found in default corpus"


@pytest.mark.unit
def test_every_case_has_why() -> None:
    suite = load_default_suite()
    for case in suite.cases:
        assert case.why and case.why.strip(), f"Case {case.id!r} has an empty 'why' field"


@pytest.mark.unit
def test_is_scored_follows_stable_when_scored_not_set() -> None:
    suite = load_default_suite()
    for case in suite.cases:
        if case.scored is None:
            assert case.is_scored == case.stable, f"Case {case.id!r}: is_scored should equal stable when scored is None"


@pytest.mark.unit
def test_is_scored_explicit_overrides_stable() -> None:
    suite = load_default_suite()
    # Find a case where scored is explicitly set
    explicit = [c for c in suite.cases if c.scored is not None]
    # The corpus may not have explicit overrides; if none exist, skip
    for case in explicit:
        assert case.is_scored == case.scored, f"Case {case.id!r}: is_scored should equal explicit scored value"


@pytest.mark.unit
def test_volatile_cases_not_scored_by_default() -> None:
    suite = load_default_suite()
    volatile = [c for c in suite.cases if not c.stable]
    for case in volatile:
        # An unstable case with no explicit scored=True should not be scored
        if case.scored is None:
            assert not case.is_scored, f"Case {case.id!r} is unstable and should not be scored by default"


@pytest.mark.unit
def test_difficulty_in_valid_range() -> None:
    suite = load_default_suite()
    for case in suite.cases:
        assert 1 <= case.difficulty <= 5, f"Case {case.id!r} has difficulty {case.difficulty} outside [1, 5]"


@pytest.mark.unit
def test_content_types_valid() -> None:
    suite = load_default_suite()
    valid_content_types = {"html", "pdf"}
    for case in suite.cases:
        assert case.content_type in valid_content_types, (
            f"Case {case.id!r} has unexpected content_type {case.content_type!r}"
        )
