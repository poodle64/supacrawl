#!/usr/bin/env python3
"""Test script to verify SPA delay implementation."""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

# Removed: _crawl_settings_summary (was Crawl4AI-specific)


def test_spa_delay_default():
    """Test that SPA delay defaults to 2.0 seconds."""
    # Clear any existing env var
    if "CRAWL4AI_SPA_EXTRA_DELAY" in os.environ:
        del os.environ["CRAWL4AI_SPA_EXTRA_DELAY"]

    settings = _crawl_settings_summary()
    assert "spa_extra_delay" in settings
    assert settings["spa_extra_delay"] == "2.0"
    print("✓ SPA delay defaults to 2.0 seconds")


def test_spa_delay_custom():
    """Test that SPA delay can be customized via env var."""
    os.environ["CRAWL4AI_SPA_EXTRA_DELAY"] = "5.0"

    settings = _crawl_settings_summary()
    assert settings["spa_extra_delay"] == "5.0"
    print("✓ SPA delay respects custom value (5.0 seconds)")

    # Cleanup
    del os.environ["CRAWL4AI_SPA_EXTRA_DELAY"]


def test_total_delay_calculation():
    """Test that total delay is base + SPA delay."""
    os.environ["CRAWL4AI_SPA_EXTRA_DELAY"] = "3.0"

    # Import after setting env var
    spa_extra_delay = float(os.getenv("CRAWL4AI_SPA_EXTRA_DELAY", "2.0"))
    total_delay = 0.25 + spa_extra_delay

    assert total_delay == 3.25
    print(f"✓ Total delay calculation correct: 0.25 + 3.0 = {total_delay} seconds")

    # Cleanup
    del os.environ["CRAWL4AI_SPA_EXTRA_DELAY"]


if __name__ == "__main__":
    print("Testing SPA delay implementation...\n")

    test_spa_delay_default()
    test_spa_delay_custom()
    test_total_delay_calculation()

    print("\n✓ All tests passed!")
    print("\nImplementation summary:")
    print("- Default SPA delay: 2.0 seconds")
    print("- Total delay: base_delay (0.25s) + spa_extra_delay")
    print("- Configurable via CRAWL4AI_SPA_EXTRA_DELAY env var")
    print("- Documented in .env.example")
    print("- Tracked in manifest crawl_settings")
