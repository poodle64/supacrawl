# PR0: Baseline Quality Harness

## Purpose

Establish a deterministic baseline harness that captures crawl quality metrics from the current implementation (Crawl4AI 0.7.8). This baseline will be used to detect quality regressions during future refactoring.

**Critical**: This PR does NOT change production crawler behaviour. It only adds test infrastructure.

---

## Files to Add/Edit

### New Files

1. **`tests/fixtures/sites/baseline-simple.yaml`**
   - Copy from `sites/sharesight-api.yaml` (simplified for fast testing)
   - Purpose: Single entrypoint, API documentation site

2. **`tests/fixtures/sites/baseline-multi.yaml`**
   - Copy from `sites/meta.yaml` (simplified for fast testing)
   - Purpose: Multiple entrypoints, complex include/exclude patterns

3. **`tests/fixtures/baseline_metrics.json`**
   - Generated file containing baseline quality metrics
   - Format: `{"site_id": {"metric_name": value, ...}, ...}`
   - Purpose: Store deterministic baseline for assertions

4. **`tests/conftest.py`**
   - Pytest configuration and fixtures
   - Purpose: Shared test utilities, fast mode config

5. **`tests/test_baseline_quality.py`**
   - Main baseline quality test suite
   - Purpose: Capture and assert against baseline metrics

### Modified Files

1. **`web_scraper/cli.py`**
   - Add `--fast-mode` flag to `crawl` command
   - Purpose: Enable fast mode for tests (reduced pages, timeouts)

2. **`web_scraper/scrapers/crawl4ai.py`**
   - Add `_fast_mode_config()` helper function (internal, not exposed)
   - Purpose: Apply fast mode settings to `SiteConfig` for testing

---

## Fixture Site Configs

### 1. `tests/fixtures/sites/baseline-simple.yaml`

**Source**: `sites/sharesight-api.yaml` (simplified)

**Exact filename**: `baseline-simple.yaml`

**Content** (derived from `sites/sharesight-api.yaml`):
```yaml
id: baseline-simple
name: Baseline Simple (Sharesight API)

entrypoints:
  - https://portfolio.sharesight.com/api

include:
  - https://portfolio.sharesight.com/api/**

exclude: []

max_pages: 10  # Reduced for fast testing (original: 500)

formats:
  - markdown

only_main_content: true
include_subdomains: false

# Disable features that slow down tests
sitemap:
  enabled: false

link_discovery_workaround:
  enabled: false  # Test without workaround

markdown_fixes:
  enabled: false  # Test raw Crawl4AI output
```

**Rationale**: 
- Single entrypoint, simple structure
- API documentation site (good for testing markdown quality)
- Fast to crawl (10 pages max)

### 2. `tests/fixtures/sites/baseline-multi.yaml`

**Source**: `sites/meta.yaml` (simplified)

**Exact filename**: `baseline-multi.yaml`

**Content** (derived from `sites/meta.yaml`):
```yaml
id: baseline-multi
name: Baseline Multi (Meta Docs)

entrypoints:
  - https://developers.facebook.com/docs/graph-api/overview
  - https://developers.facebook.com/docs/graph-api/get-started

include:
  - https://developers.facebook.com/docs/graph-api/**

exclude:
  - https://developers.facebook.com/tools/**
  - https://developers.facebook.com/docs/**/changelog**

max_pages: 15  # Reduced for fast testing (original: 200)

formats:
  - markdown

only_main_content: true
include_subdomains: false

# Disable features that slow down tests
sitemap:
  enabled: false

link_discovery_workaround:
  enabled: false

markdown_fixes:
  enabled: false

# Keep cleaning config for quality testing
cleaning:
  skip_until_heading: true
```

**Rationale**:
- Multiple entrypoints, complex include/exclude patterns
- Tests deep crawl strategy
- Fast to crawl (15 pages max)

### 3. `tests/fixtures/sites/baseline-single-page.yaml`

**Source**: New minimal config

**Exact filename**: `baseline-single-page.yaml`

**Content**:
```yaml
id: baseline-single-page
name: Baseline Single Page

entrypoints:
  - https://example.com

include:
  - https://example.com

exclude: []

max_pages: 1

formats:
  - markdown

only_main_content: true
include_subdomains: false

sitemap:
  enabled: false

link_discovery_workaround:
  enabled: false

markdown_fixes:
  enabled: false
```

**Rationale**:
- Minimal config for smoke testing
- Very fast (1 page)
- Tests basic crawl functionality

---

## Quality Metrics Definition

### Metrics to Capture (Non-Brittle)

All metrics are calculated from the **first page** of each crawl result to ensure determinism.

#### 1. **Page Count Metrics**
- `total_pages`: Total number of pages crawled (int)
- `unique_urls`: Number of unique URLs (int, deduplicated)
- **Threshold**: `total_pages >= 1` (at least one page must be crawled)

#### 2. **Content Size Metrics**
- `avg_word_count`: Average words per page (float)
- `avg_char_count`: Average characters per page (float)
- `min_word_count`: Minimum words in any page (int)
- `max_word_count`: Maximum words in any page (int)
- **Threshold**: `avg_word_count >= 50` (pages must have meaningful content)

#### 3. **Structure Metrics**
- `avg_heading_count`: Average headings per page (float)
- `pages_with_headings`: Number of pages with at least one heading (int)
- `avg_code_block_count`: Average code blocks per page (float)
- `pages_with_code`: Number of pages with at least one code block (int)
- **Threshold**: `pages_with_headings >= total_pages * 0.5` (at least 50% of pages have headings)

#### 4. **Link Metrics**
- `avg_link_count`: Average links per page (float)
- `avg_link_density`: Average link density (links/words, float)
- **Threshold**: `avg_link_density <= 0.3` (not too navigation-heavy)

#### 5. **Content Quality Metrics**
- `avg_boilerplate_score`: Average boilerplate score (0.0-1.0, float)
  - Calculated from keywords: "cookie", "privacy policy", "terms", "navigation", "menu", "footer", "sidebar", "advertisement", "subscribe", "newsletter", "social media", "on this page"
  - Lower is better
- `avg_content_density`: Average content density (non-empty lines / total lines, float)
- `pages_with_main_content`: Number of pages with main content indicators (int)
  - Indicators: H2 headings, code blocks, API references
- **Threshold**: `avg_boilerplate_score <= 0.4` (not too much boilerplate)

#### 6. **Format Metrics**
- `markdown_files_written`: Number of markdown files in snapshot (int)
- `manifest_exists`: Whether manifest.json exists (bool)
- `manifest_page_count`: Number of pages in manifest (int)
- **Threshold**: `manifest_page_count == total_pages` (manifest matches actual pages)

#### 7. **Determinism Metrics**
- `content_hash_stable`: Whether content hashes are consistent across runs (bool)
  - Run crawl twice, compare hashes
- `url_normalization_stable`: Whether URLs are normalized consistently (bool)
  - Check that URLs match expected patterns

### Metric Calculation Functions

**Location**: `tests/test_baseline_quality.py`

**Functions**:
- `calculate_page_metrics(pages: list[Page]) -> dict[str, Any]`
- `calculate_content_metrics(pages: list[Page]) -> dict[str, Any]`
- `calculate_structure_metrics(pages: list[Page]) -> dict[str, Any]`
- `calculate_quality_metrics(pages: list[Page]) -> dict[str, Any]`
- `calculate_format_metrics(snapshot_path: Path) -> dict[str, Any]`

**Reference**: Based on `tests/test_crawl4ai_quality.py::_calculate_quality_metrics()` but extended for baseline capture.

---

## Fast Mode Implementation

### Fast Mode Configuration

**Location**: `web_scraper/scrapers/crawl4ai.py`

**Function**: `_apply_fast_mode_config(config: SiteConfig) -> SiteConfig`

**Changes**:
1. Reduce `max_pages` to `min(config.max_pages, 5)` (cap at 5 pages)
2. Disable `sitemap.enabled` (skip sitemap discovery)
3. Disable `link_discovery_workaround.enabled` (skip workaround)
4. Set `rate_limit.requests_per_second = 10.0` (faster rate limiting)
5. Set `rate_limit.per_domain_delay = 0.1` (minimal delay)
6. Set `browser_pool.pool_size = 1` (single browser)
7. Set `CRAWL4AI_ENTRYPOINT_TIMEOUT_MS = 30000` (30s timeout, via env var)

**Usage**: Internal function, called from `Crawl4AIScraper.crawl()` when `fast_mode=True` parameter is passed.

**CLI Integration**: `web_scraper/cli.py::crawl()` command accepts `--fast-mode` flag that sets `fast_mode=True` in scraper.

**Note**: Fast mode is **only** for testing. Production crawls never use fast mode.

### Fast Mode Flag

**Location**: `web_scraper/cli.py`

**Change**: Add `--fast-mode` option to `crawl` command:

```python
@click.option(
    "--fast-mode",
    is_flag=True,
    default=False,
    help="Enable fast mode for testing (reduced pages, timeouts).",
)
def crawl(
    ...,
    fast_mode: bool,
) -> None:
    ...
    scraper = Crawl4AIScraper(...)
    # Pass fast_mode to scraper (requires adding fast_mode parameter to crawl method)
```

**Alternative**: Since we don't want to change production behaviour, fast mode can be implemented as:
- Environment variable: `WEB_SCRAPER_FAST_MODE=true`
- Or internal test-only function that modifies config before crawling

**Recommendation**: Use environment variable approach to avoid changing production code.

---

## Test Structure

### Test File: `tests/test_baseline_quality.py`

**Structure**:

```python
"""Baseline quality harness for detecting crawl quality regressions."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from web_scraper.models import SiteConfig
from web_scraper.scrapers.crawl4ai import Crawl4AIScraper
from web_scraper.sites.loader import load_site_config

# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SITES_DIR = FIXTURES_DIR / "sites"
BASELINE_METRICS_FILE = FIXTURES_DIR / "baseline_metrics.json"

# Test site configs
BASELINE_SITES = [
    "baseline-simple",
    "baseline-multi",
    "baseline-single-page",
]


@pytest.fixture(scope="session")
def baseline_metrics() -> dict[str, Any]:
    """Load baseline metrics from fixture file."""
    if BASELINE_METRICS_FILE.exists():
        return json.loads(BASELINE_METRICS_FILE.read_text())
    return {}


def calculate_all_metrics(pages: list[Page], snapshot_path: Path) -> dict[str, Any]:
    """Calculate all quality metrics for a crawl."""
    # Combine all metric calculations
    ...


@pytest.mark.parametrize("site_id", BASELINE_SITES)
def test_baseline_quality_capture(site_id: str, tmp_path: Path) -> None:
    """
    Capture baseline quality metrics from current implementation.
    
    Run this test once to establish baseline, then commit baseline_metrics.json.
    """
    # Only run if WEB_SCRAPER_CAPTURE_BASELINE env var is set
    if not os.getenv("WEB_SCRAPER_CAPTURE_BASELINE"):
        pytest.skip("Set WEB_SCRAPER_CAPTURE_BASELINE=1 to capture baseline")
    
    # Load site config
    config = load_site_config(site_id, SITES_DIR)
    
    # Enable fast mode via env var
    os.environ["WEB_SCRAPER_FAST_MODE"] = "true"
    
    # Crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Calculate metrics
    metrics = calculate_all_metrics(pages, snapshot_path)
    
    # Load existing baseline
    baseline = {}
    if BASELINE_METRICS_FILE.exists():
        baseline = json.loads(BASELINE_METRICS_FILE.read_text())
    
    # Update baseline for this site
    baseline[site_id] = metrics
    
    # Save baseline
    BASELINE_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_METRICS_FILE.write_text(json.dumps(baseline, indent=2))
    
    # Assertions (basic sanity checks)
    assert len(pages) > 0, f"{site_id}: No pages crawled"
    assert metrics["avg_word_count"] >= 50, f"{site_id}: Insufficient content"


@pytest.mark.parametrize("site_id", BASELINE_SITES)
def test_baseline_quality_assert(baseline_metrics: dict[str, Any], site_id: str, tmp_path: Path) -> None:
    """
    Assert current crawl quality matches baseline.
    
    This test runs on every CI run to detect regressions.
    """
    # Skip if baseline not captured
    if site_id not in baseline_metrics:
        pytest.skip(f"Baseline not captured for {site_id}")
    
    # Load site config
    config = load_site_config(site_id, SITES_DIR)
    
    # Enable fast mode via env var
    os.environ["WEB_SCRAPER_FAST_MODE"] = "true"
    
    # Crawl
    scraper = Crawl4AIScraper()
    pages, snapshot_path = scraper.crawl(config, corpora_dir=tmp_path)
    
    # Calculate metrics
    current_metrics = calculate_all_metrics(pages, snapshot_path)
    baseline = baseline_metrics[site_id]
    
    # Assertions with thresholds (not exact matches)
    assert current_metrics["total_pages"] >= baseline["total_pages"] * 0.8, \
        f"{site_id}: Page count dropped significantly"
    
    assert current_metrics["avg_word_count"] >= baseline["avg_word_count"] * 0.8, \
        f"{site_id}: Content size dropped significantly"
    
    assert current_metrics["pages_with_headings"] >= baseline["pages_with_headings"] * 0.8, \
        f"{site_id}: Heading structure degraded"
    
    assert current_metrics["avg_boilerplate_score"] <= baseline["avg_boilerplate_score"] * 1.2, \
        f"{site_id}: Boilerplate increased significantly"
    
    # Format assertions (exact matches)
    assert current_metrics["manifest_exists"] == baseline["manifest_exists"], \
        f"{site_id}: Manifest existence changed"
    
    assert current_metrics["manifest_page_count"] == current_metrics["total_pages"], \
        f"{site_id}: Manifest page count mismatch"
```

---

## Acceptance Criteria

### Functional Requirements

1. ✅ **Baseline capture works**: Running `WEB_SCRAPER_CAPTURE_BASELINE=1 pytest tests/test_baseline_quality.py::test_baseline_quality_capture` generates `tests/fixtures/baseline_metrics.json`

2. ✅ **Baseline assertion works**: Running `pytest tests/test_baseline_quality.py::test_baseline_quality_assert` compares current metrics against baseline

3. ✅ **Fast mode works**: Tests complete in < 60 seconds per site config

4. ✅ **Metrics are deterministic**: Running the same crawl twice produces identical metrics (within tolerance)

5. ✅ **No production changes**: Production crawler behaviour is unchanged (fast mode only affects tests)

### Quality Requirements

1. ✅ **Metrics are non-brittle**: Assertions use thresholds (80% of baseline) not exact matches

2. ✅ **Metrics cover key areas**: Page count, content size, structure, links, quality, format, determinism

3. ✅ **Fixtures are representative**: 3 fixture sites cover single-page, simple multi-page, and complex multi-entrypoint scenarios

4. ✅ **Baseline is committed**: `tests/fixtures/baseline_metrics.json` is committed to version control

### Technical Requirements

1. ✅ **Tests are isolated**: Each test uses `tmp_path` for corpora output

2. ✅ **Tests are fast**: Fast mode reduces crawl time to < 60s per site

3. ✅ **Tests are reliable**: Tests don't depend on external network state (use real URLs but tolerate failures)

4. ✅ **Code is documented**: All functions have docstrings explaining metric calculations

5. ✅ **Fixtures are minimal**: Site configs are simplified versions of production configs

### Verification Steps

1. **Capture baseline**:
   ```bash
   WEB_SCRAPER_CAPTURE_BASELINE=1 pytest tests/test_baseline_quality.py::test_baseline_quality_capture -v
   ```
   - Verify `tests/fixtures/baseline_metrics.json` is created
   - Verify metrics look reasonable (word counts > 0, etc.)

2. **Assert against baseline**:
   ```bash
   pytest tests/test_baseline_quality.py::test_baseline_quality_assert -v
   ```
   - Verify all assertions pass
   - Verify tests complete in < 3 minutes total

3. **Verify fast mode**:
   ```bash
   time pytest tests/test_baseline_quality.py::test_baseline_quality_assert -v
   ```
   - Verify total time < 3 minutes for all 3 sites

4. **Verify no production changes**:
   ```bash
   # Run production crawl (no fast mode)
   web-scraper crawl sharesight-api --verbose
   # Verify behaviour unchanged (same pages, same quality)
   ```

5. **Verify determinism**:
   ```bash
   # Run same test twice
   pytest tests/test_baseline_quality.py::test_baseline_quality_assert::test_baseline_quality_assert[baseline-single-page] -v
   pytest tests/test_baseline_quality.py::test_baseline_quality_assert::test_baseline_quality_assert[baseline-single-page] -v
   # Verify metrics are identical (or within small tolerance)
   ```

---

## Implementation Notes

### Fast Mode Implementation Strategy

**Option 1: Environment Variable (Recommended)**
- Add `WEB_SCRAPER_FAST_MODE` env var check in `Crawl4AIScraper.crawl()`
- Modify `SiteConfig` internally before crawling
- No CLI changes needed
- **Pros**: No production code changes, test-only feature
- **Cons**: Requires internal config modification

**Option 2: Internal Helper Function**
- Add `_apply_fast_mode_config()` in `crawl4ai.py`
- Call from test code only (not exposed in CLI)
- **Pros**: Explicit, test-only
- **Cons**: Requires test code to modify config

**Recommendation**: Use Option 1 (environment variable) to avoid any production code changes.

### Metric Calculation Reference

**Existing code**: `tests/test_crawl4ai_quality.py::_calculate_quality_metrics()`

**Extend with**:
- Page count metrics (from `pages` list)
- Format metrics (from `snapshot_path` filesystem)
- Determinism metrics (from multiple runs)

### Baseline File Format

**Location**: `tests/fixtures/baseline_metrics.json`

**Format**:
```json
{
  "baseline-simple": {
    "total_pages": 8,
    "unique_urls": 8,
    "avg_word_count": 342.5,
    "avg_char_count": 2156.2,
    "min_word_count": 120,
    "max_word_count": 567,
    "avg_heading_count": 4.2,
    "pages_with_headings": 8,
    "avg_code_block_count": 2.1,
    "pages_with_code": 6,
    "avg_link_count": 12.3,
    "avg_link_density": 0.036,
    "avg_boilerplate_score": 0.15,
    "avg_content_density": 0.78,
    "pages_with_main_content": 8,
    "markdown_files_written": 8,
    "manifest_exists": true,
    "manifest_page_count": 8
  },
  "baseline-multi": { ... },
  "baseline-single-page": { ... }
}
```

---

## Files Summary

### New Files (5)
1. `tests/fixtures/sites/baseline-simple.yaml`
2. `tests/fixtures/sites/baseline-multi.yaml`
3. `tests/fixtures/sites/baseline-single-page.yaml`
4. `tests/fixtures/baseline_metrics.json` (generated, committed)
5. `tests/test_baseline_quality.py`

### Modified Files (1)
1. `web_scraper/scrapers/crawl4ai.py` (add fast mode support via env var)

### No Changes
- `web_scraper/cli.py` (no CLI changes needed if using env var)
- Production crawler behaviour (unchanged)

---

**Status**: Ready for implementation. All file paths, functions, and metrics are specified with exact references to existing code.
