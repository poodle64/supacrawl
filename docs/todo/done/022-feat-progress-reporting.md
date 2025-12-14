# 022: Add Progress Reporting

## Status

✅ DONE (2025-12-13)

## Problem Summary

Current crawl output is minimal:

```
Starting crawl: meta-docs (meta) with 20 entrypoints...
Finished crawl: meta-docs -> 150 pages
Snapshot created at corpora/meta-docs/20250115T143000
```

Users don't know:
- How many pages have been crawled so far
- Estimated time remaining
- Current URL being processed
- Error rates
- Pages per second

This makes long crawls frustrating and debugging difficult.

## Solution Overview

Add rich progress reporting:

1. Progress bar with ETA
2. Current URL display
3. Statistics (pages/sec, errors, etc.)
4. Verbose mode with per-page details
5. Summary at completion

## Implementation Steps

### Create Progress Reporter

- [ ] Create `web_scraper/progress.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class CrawlProgress:
    total_pages: int | None = None  # Unknown until sitemap/discovery
    completed_pages: int = 0
    failed_pages: int = 0
    current_url: str | None = None
    start_time: datetime = None
    pages_per_second: float = 0.0
    
    @property
    def eta(self) -> timedelta | None:
        if not self.total_pages or not self.pages_per_second:
            return None
        remaining = self.total_pages - self.completed_pages
        return timedelta(seconds=remaining / self.pages_per_second)

class ProgressReporter:
    """Report crawl progress to console."""
    
    def __init__(self, verbose: bool = False, show_progress: bool = True):
        ...
    
    def start(self, total_pages: int | None = None) -> None:
        ...
    
    def update(self, url: str, status: str = "ok") -> None:
        ...
    
    def finish(self) -> None:
        ...
```

### Integrate with Click

- [ ] Use `rich` library for beautiful progress bars
- [ ] Fallback to simple text for non-TTY
- [ ] Integrate with `--verbose` flag

### Progress Display Modes

- [ ] **Normal mode**: Progress bar with basic stats

```
Crawling: [████████████░░░░░░░░] 45/100 pages | 2.3 p/s | ETA: 00:24
```

- [ ] **Verbose mode**: Per-page details

```
[14:30:01] ✓ https://example.com/page1 (1.2s)
[14:30:03] ✓ https://example.com/page2 (0.8s)
[14:30:04] ✗ https://example.com/page3 - 404 Not Found
```

### Statistics Tracking

- [ ] Total pages crawled
- [ ] Pages per second
- [ ] Average response time
- [ ] Error count by type
- [ ] Content size (bytes/chars)

### Summary Output

- [ ] Show summary at crawl completion:

```
Crawl Complete
==============
Duration:     00:02:34
Total Pages:  150
Successful:   145
Failed:       5
Content Size: 2.3 MB
Avg Time:     1.2s/page
Snapshot:     corpora/meta-docs/20250115T143000
```

### CLI Updates

- [ ] Add `--progress/--no-progress` flag
- [ ] Add `--stats` flag for detailed statistics
- [ ] Update `--verbose` to show per-page details

## Files to Modify

- Create `web_scraper/progress.py`
- Update `web_scraper/cli.py` - Integrate progress
- Update `web_scraper/scrapers/crawl4ai.py` - Report progress
- Update `pyproject.toml` - Add `rich` dependency

## Testing Considerations

- Test progress bar rendering
- Test ETA calculation accuracy
- Test non-TTY output (CI environments)
- Test verbose mode output
- Test with unknown total (no sitemap)

## Success Criteria

- [ ] Progress bar shows during crawl
- [ ] ETA is displayed when total known
- [ ] Verbose mode shows per-page details
- [ ] Summary displayed at completion
- [ ] Works in non-TTY environments
- [ ] Documentation covers progress options

## References

- Rich library: https://rich.readthedocs.io/
- Click progress: https://click.palletsprojects.com/en/8.1.x/utils/#showing-progress-bars

