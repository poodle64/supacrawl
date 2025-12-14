# Cross-page boilerplate fingerprinting

## ✅ STATUS: DONE

**Created**: 2025-12-12  
**Completed**: 2025-12-12  
**Type**: feat

### Outcome

- Added block fingerprinting and cross-page boilerplate detection to the snapshot writer.
- Rewrites pages to remove repeated headers/footers with a 40% safety cap and logs boilerplate stats.
- Manifest/run log now list boilerplate hashes; new tests cover removal and guardrail behaviour.

## Problem Summary

Repeated headers/footers/CTAs reappear across pages. Site-specific filters don’t scale. We need automatic detection of repeated blocks across the crawl and removal before writing markdown.

## Solution Overview

Fingerprint normalized text blocks per page, detect repeats across ≥2 pages, and mark them as boilerplate. On subsequent pages (and retroactively within the run), drop those blocks prior to hashing/writing. Persist boilerplate hashes/stats in the snapshot for auditability.

## Implementation Steps

### 1. Block hashing and collection

- **File**: `web_scraper/corpus/writer.py`
- Split cleaned HTML/Markdown into top-level sections (e.g., by heading or DOM blocks) and compute stable hashes (normalized text, stripped links).
- Store per-page block hashes alongside page metadata (in-memory during run).

### 2. Boilerplate detection across pages

- **File**: `web_scraper/corpus/writer.py`
- Track frequency of each block hash; once a hash is seen on ≥2 pages in the same run, classify as boilerplate.
- Record boilerplate hash list and counts in manifest/run log.

### 3. Boilerplate removal and rewrite

- **File**: `web_scraper/scrapers/crawl4ai.py`
- Before finalizing a page, remove sections matching known boilerplate hashes; recompute page hash and stats.
- If boilerplate is discovered after earlier pages were written, rewrite those pages within the snapshot (or mark a “boilerplate_removed” revision entry) to keep consistency.

### 4. Telemetry and guardrails

- **File**: `web_scraper/corpus/writer.py`
- Emit per-page boilerplate ratio in run log; cap removals to avoid stripping >40% of content; warn when caps are hit.

## Files to Modify

1. `web_scraper/corpus/writer.py`
2. `web_scraper/scrapers/crawl4ai.py`

## Testing Considerations

- Fixtures with shared header/footer blocks across 3 pages; assert only unique article bodies remain.
- Ensure boilerplate cap prevents over-stripping on tiny pages.
- Verify manifest/run log includes boilerplate stats and rewritten pages are consistent.

## Success Criteria

- Repeated nav/footer/CTA blocks are removed automatically without site-specific rules.
- Snapshot manifest/run log show boilerplate hashes and ratios; page hashes reflect cleaned content.
- No accidental removal of unique article sections (guardrail cap holds).

## References

- `docs/master/todo/README.md`  
- `web_scraper/corpus/writer.py` (snapshot writer)  
- `web_scraper/scrapers/crawl4ai.py` (page cleaning pipeline)
