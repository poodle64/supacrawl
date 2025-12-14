# Readability-style main content extraction

## ✅ STATUS: DONE

**Created**: 2025-12-12  
**Completed**: 2025-12-12  
**Type**: feat

### Outcome

- Implemented DOM readability scoring with canonical URL handling and tracker stripping.
- Added markdown sanitizer to drop nav/link-heavy blocks and emit content stats.
- Added unit coverage for canonical selection, main content extraction, and nav pruning.

## Problem Summary

Current Crawl4AI markdown keeps nav/footer noise unless we hardcode site-specific filters. We need a site-agnostic readability-style extractor that isolates the real article body before Markdown conversion and trims leftover boilerplate after conversion.

## Solution Overview

Implement a DOM scoring pipeline (tag weights, text density, link density, class/role hints, DOM position) to select the main content container(s) before Markdown generation. After Markdown, run a structural sanitizer to trim navigation/“on this page” fragments and enforce a clean heading window. Include canonical URL normalization to improve dedupe and hashing.

## Implementation Steps

### 1. DOM readability scorer

**File**: `web_scraper/scrapers/crawl4ai.py` (or helper module)  
**File**: `web_scraper/scrapers/crawl4ai_result.py`

- Parse rendered HTML and score block-level nodes by:
  - Tag weights (article/main/section/h1–h3/p/pre/table positive; nav/footer/aside negative)
  - Text density vs link density (penalize link-heavy/short blocks)
  - Role/class/id hints (`nav`, `menu`, `footer`, `breadcrumb`, `banner`, `cookie`, `social` negative; `content`, `article`, `doc` positive)
  - Position heuristics (demote very top/bottom repeated blocks)
- Select top-scoring container(s), drop siblings with low scores, and pass the reduced HTML to Markdown generator.
- Make scorer configurable (thresholds/weights) and log chosen node info to run log.

### 2. Post-Markdown structural sanitizer

**File**: `web_scraper/scrapers/crawl4ai.py`

- Trim content window from first `#` heading to last meaningful section.
- Remove sections whose link density exceeds a threshold (e.g., >0.5) to drop nav tables.
- Collapse duplicate blank lines; preserve code fences/tables; keep images only if they have alt/caption context.
- Emit per-page stats: text length, link density, heading count.

### 3. Canonical URL normalization

**File**: `web_scraper/scrapers/crawl4ai_result.py`

- Read `<link rel="canonical">` and normalize URLs (strip `utm_*`, `fbclid` etc).
- Use canonical for dedupe/hash/storage where available; fall back to fetched URL.

## Files to Modify

1. `web_scraper/scrapers/crawl4ai.py`
2. `web_scraper/scrapers/crawl4ai_result.py`

## Testing Considerations

- Unit tests for scoring heuristics given sample HTML fixtures (nav + article + footer).
- Ensure code fences/tables survive sanitizer (golden markdown comparison).
- Verify canonical normalization strips tracking params and preserves path/query integrity.
- Regression: crawl `sites/meta-overview.yaml` and confirm nav/footer are absent without site-specific rules.

## Success Criteria

- Single-page crawls emit markdown without nav/footer/social blocks, using generic heuristics.
- Canonical URLs used for dedupe; tracking params removed in manifest/run logs.
- Sanitizer leaves code/table content intact while removing link-heavy nav.

## References

- `docs/master/todo/README.md` (format rules)  
- `web_scraper/scrapers/crawl4ai.py` (current cleaning)  
- `web_scraper/scrapers/crawl4ai_result.py` (page extraction)  
