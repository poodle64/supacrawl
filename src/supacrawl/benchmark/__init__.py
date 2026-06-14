"""Scrape-quality benchmark for supacrawl.

This package measures how faithfully supacrawl converts real web pages into
clean markdown. It scrapes a curated corpus of test sites, captures what a real
browser renders as the ground truth, and scores supacrawl's output against it on
completeness, noise, and structure retention. Results are persisted per run so
quality can be tracked over time and runs compared.

The public surface is intentionally small:

- ``models`` — the input (corpus) and output (run result) data contracts.
- ``metrics`` — pure functions computing fidelity metrics from text.
- ``runner`` — orchestrates a run over the corpus.
- ``store`` — persists and reloads run results, and compares runs.
"""

from supacrawl.benchmark.models import (
    SCHEMA_VERSION,
    BenchCase,
    BenchSuite,
    CaseMetrics,
    CaseResult,
    RunAggregate,
    RunResult,
)

__all__ = [
    "SCHEMA_VERSION",
    "BenchCase",
    "BenchSuite",
    "CaseMetrics",
    "CaseResult",
    "RunAggregate",
    "RunResult",
]
