# Crawl resilience, expansion, and language enforcement

## ✅ STATUS: DONE

**Created**: 2025-12-12  
**Completed**: 2025-12-12  
**Type**: feat

### Outcome

- Added tracker-block pattern support, DOM auto-expansion helper, and adaptive language enforcement with paragraph filtering.
- Language stats (code, confidence, action) flow into page extras and manifests; fetch stats hook wired for telemetry.
- Added tests for language detection and boilerplate resilience updates.

## Problem Summary

Some docs hide content behind “expand” controls, load slowly, or serve localized variants. We need resilient fetch/interaction, ad/tracker blocking, and enforced English output with basic language QA.

## Solution Overview

Add controlled DOM expansion, adaptive wait strategies, request blocking for trackers, iframe handling, and lightweight language detection with optional re-fetch or paragraph filtering. Emit per-page language and fetch stats.

## Implementation Steps

### 1. Interactive expansion & adaptive wait

**File**: `web_scraper/scrapers/crawl4ai.py`

- Before extraction, click common expanders (`details`, buttons with “Show more”, `[data-testid*="expand"]`) up to a capped count; short wait after clicks.
- Wait strategy: network-idle OR presence of main/article selectors; fallback scroll pass.
- Log expansions performed and wait condition hit.

### 2. Request blocking and iframe policy

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Block analytics/ad/tracker domains (doubleclick, analytics, pixel, scontent.fb, etc.).
- Allow iframe capture for same-origin or whitelisted doc hosts; otherwise ignore.

### 3. Language enforcement and QA

**File**: `web_scraper/scrapers/crawl4ai.py`

- After cleaning, run fast language detection (fastText/CLD3). If not English:
  - Optional re-fetch with stronger `Accept-Language`/query params where applicable, or
  - Drop non-English paragraphs if mixed.
- Record detected language, confidence, and action taken in run log and manifest.

### 4. Telemetry

**File**: `web_scraper/corpus/writer.py`

- Add fetch stats (expansions count, blocked requests count, language, text length) to per-page metadata.

## Files to Modify

1. `web_scraper/scrapers/crawl4ai.py`
2. `web_scraper/scrapers/crawl4ai_config.py`
3. `web_scraper/corpus/writer.py`

## Testing Considerations

- Fixture with collapsible sections: ensure expanded content appears in markdown.
- Ensure tracker blocking doesn’t break page load; verify counts logged.
- Language detection: mixed-language fixture should be flagged; EN-only stays untouched.

## Success Criteria

- Hidden sections surfaced; markdown includes expanded content.
- Tracker requests blocked; page still succeeds.
- Language field recorded as English for target pages; non-English detected and handled per policy.

## References

- `docs/master/todo/README.md`  
- `web_scraper/scrapers/crawl4ai.py`  
- `web_scraper/scrapers/crawl4ai_config.py`  
- `web_scraper/corpus/writer.py`
