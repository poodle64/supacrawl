"""Corpus loaders for the scrape-quality benchmark.

Provides two entry points:

- ``load_default_suite`` — the curated default corpus shipped with the package.
- ``load_suite`` — an arbitrary YAML file on disk.

Both return a validated ``BenchSuite`` so callers never deal with raw dicts.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from supacrawl.benchmark.models import BenchSuite


def load_default_suite() -> BenchSuite:
    """Load the packaged default benchmark corpus.

    Returns:
        Validated ``BenchSuite`` from the built-in ``corpus/default.yaml``.

    Raises:
        ValueError: If the YAML is malformed or fails Pydantic validation.
    """
    resource = files("supacrawl.benchmark").joinpath("corpus").joinpath("default.yaml")
    raw = resource.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    return BenchSuite.model_validate(data)


def load_suite(path: Path) -> BenchSuite:
    """Load a benchmark suite from an arbitrary YAML file on disk.

    Args:
        path: Absolute or relative path to the suite YAML file.

    Returns:
        Validated ``BenchSuite`` from the given file.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the YAML is malformed or fails Pydantic validation.
    """
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    return BenchSuite.model_validate(data)
