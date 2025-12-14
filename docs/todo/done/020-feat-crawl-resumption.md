# 020: Add Crawl Resumption Support

## Status

📋 PLANNING

## Problem Summary

If a crawl of 200 pages fails at page 150:

1. The `IncrementalSnapshotWriter` saves progress (pages 1-150)
2. But there's no way to resume from page 151
3. Re-running crawls the entire site again
4. Wastes time and may trigger rate limiting

The current system has partial infrastructure (incremental writing, run logs) but lacks the resumption logic.

## Solution Overview

Add crawl resumption:

1. Track completed URLs in snapshot
2. Add `--resume` flag to crawl command
3. Load existing snapshot and skip completed URLs
4. Continue crawling from where it stopped
5. Merge new pages into existing snapshot

## Implementation Steps

### Track Crawl State

- [ ] Add `crawl_state.json` to snapshot:

```json
{
  "status": "in_progress",
  "completed_urls": ["url1", "url2", ...],
  "pending_urls": ["url3", "url4", ...],
  "failed_urls": [{"url": "url5", "error": "timeout"}],
  "last_updated": "2025-01-15T14:30:00",
  "checkpoint_page": 150
}
```

- [ ] Update state after each page
- [ ] Include pending URLs from deep crawl queue

### Add Resume Logic

- [ ] Create `load_crawl_state()` function
- [ ] Filter out already-completed URLs
- [ ] Resume deep crawl from pending URLs
- [ ] Handle failed URLs (retry or skip)

### CLI Updates

- [ ] Add `--resume` flag to crawl command:

```bash
web-scraper crawl meta --resume  # Resume latest in-progress crawl
web-scraper crawl meta --resume 20250115T143000  # Resume specific snapshot
```

- [ ] Add `--retry-failed` flag to retry previously failed URLs
- [ ] Show resume information in output

### Update IncrementalSnapshotWriter

- [ ] Accept existing snapshot ID for resumption
- [ ] Load existing pages and state
- [ ] Merge new pages with existing
- [ ] Update manifest incrementally

### Handle Edge Cases

- [ ] Completed snapshot (status=completed) - warn and offer fresh crawl
- [ ] Aborted snapshot (status=aborted) - allow resume or fresh start
- [ ] Changed config since snapshot - warn about differences
- [ ] URL normalization consistency

## Files to Modify

- `web_scraper/corpus/writer.py` - Add state tracking, resume loading
- `web_scraper/scrapers/crawl4ai.py` - URL filtering for completed
- `web_scraper/cli.py` - Add --resume flag
- Create `web_scraper/corpus/state.py` for state management
- Update docs

## Testing Considerations

- Test resume with completed snapshot (should warn)
- Test resume with in-progress snapshot
- Test resume with new URLs added to site
- Test retry-failed functionality
- Test state file corruption handling

## Success Criteria

- [ ] Crawl state is saved incrementally
- [ ] `--resume` continues from last checkpoint
- [ ] Completed URLs are not re-fetched
- [ ] Manifest reflects all pages (old + new)
- [ ] Failed URLs can be retried
- [ ] Documentation covers resume workflow

## References

- `.cursor/rules/40-corpus-layout-patterns-web-scraper.mdc`

