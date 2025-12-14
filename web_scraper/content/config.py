"""Configuration for content extraction and processing.

This module provides configurable thresholds and settings for content
extraction, replacing hardcoded magic numbers throughout the codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get_int_env(name: str, default: int) -> int:
    """Get integer from environment variable with default."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float_env(name: str, default: float) -> float:
    """Get float from environment variable with default."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class ExtractionConfig:
    """
    Configuration for content extraction thresholds.

    All settings can be overridden via environment variables.
    Use ExtractionConfig.from_env() to load with overrides.

    Attributes:
        nav_skip_lines: Lines to skip at start (likely navigation). Default: 5
        max_headings_to_extract: Maximum headings to collect from raw markdown. Default: 15
        max_headings_to_restore: Maximum headings to prepend if filtered. Default: 10
        min_text_for_link_penalty: Minimum text length before link density penalty. Default: 120
        link_density_penalty_threshold: Link density to trigger penalties. Default: 0.3
        nav_block_link_density: Link density that marks a block as navigation. Default: 0.5
        text_length_score_divisor: Divisor for text length scoring. Default: 500
        max_text_length_score: Maximum bonus from text length. Default: 6.0
        min_block_word_count: Minimum words to keep a block. Default: 120
        min_english_stopword_ratio: Minimum ratio for English detection. Default: 0.2
    """

    # Navigation detection
    nav_skip_lines: int = 5
    max_headings_to_extract: int = 15
    max_headings_to_restore: int = 10

    # Block scoring thresholds
    min_text_for_link_penalty: int = 120
    link_density_penalty_threshold: float = 0.3
    nav_block_link_density: float = 0.5

    # Text length scoring
    text_length_score_divisor: int = 500
    max_text_length_score: float = 6.0

    # Sanitisation thresholds
    min_block_word_count: int = 120

    # Language detection
    min_english_stopword_ratio: float = 0.2

    @classmethod
    def from_env(cls) -> ExtractionConfig:
        """
        Load configuration with environment variable overrides.

        Environment variables:
            SCRAPER_NAV_SKIP_LINES: Lines to skip at start
            SCRAPER_MAX_HEADINGS_EXTRACT: Max headings to extract
            SCRAPER_MAX_HEADINGS_RESTORE: Max headings to restore
            SCRAPER_MIN_TEXT_LINK_PENALTY: Min text for link penalty
            SCRAPER_LINK_DENSITY_THRESHOLD: Link density threshold
            SCRAPER_NAV_LINK_DENSITY: Nav block link density
            SCRAPER_TEXT_SCORE_DIVISOR: Text length score divisor
            SCRAPER_MAX_TEXT_SCORE: Max text length score
            SCRAPER_MIN_BLOCK_WORDS: Min block word count
            SCRAPER_MIN_ENGLISH_RATIO: Min English stopword ratio

        Returns:
            ExtractionConfig with environment overrides applied.
        """
        return cls(
            nav_skip_lines=_get_int_env("SCRAPER_NAV_SKIP_LINES", 5),
            max_headings_to_extract=_get_int_env("SCRAPER_MAX_HEADINGS_EXTRACT", 15),
            max_headings_to_restore=_get_int_env("SCRAPER_MAX_HEADINGS_RESTORE", 10),
            min_text_for_link_penalty=_get_int_env("SCRAPER_MIN_TEXT_LINK_PENALTY", 120),
            link_density_penalty_threshold=_get_float_env(
                "SCRAPER_LINK_DENSITY_THRESHOLD", 0.3
            ),
            nav_block_link_density=_get_float_env("SCRAPER_NAV_LINK_DENSITY", 0.5),
            text_length_score_divisor=_get_int_env("SCRAPER_TEXT_SCORE_DIVISOR", 500),
            max_text_length_score=_get_float_env("SCRAPER_MAX_TEXT_SCORE", 6.0),
            min_block_word_count=_get_int_env("SCRAPER_MIN_BLOCK_WORDS", 120),
            min_english_stopword_ratio=_get_float_env("SCRAPER_MIN_ENGLISH_RATIO", 0.2),
        )


# Default configuration instance (can be overridden at runtime)
DEFAULT_CONFIG: ExtractionConfig = field(default_factory=ExtractionConfig)


def get_config() -> ExtractionConfig:
    """
    Get the current extraction configuration.

    On first call, loads from environment variables.
    Subsequent calls return cached config.

    Returns:
        ExtractionConfig instance.
    """
    return ExtractionConfig.from_env()

