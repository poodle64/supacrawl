# Corpus Layout System

## Why Corpus Layout Exists

The corpus layout system provides a consistent, snapshot-based structure for storing scraped content, enabling:

- **Reproducibility**: Each crawl creates a timestamped snapshot
- **Versioning**: Track content changes over time
- **Downstream Integration**: Standard structure for LLM consumers
- **Metadata Preservation**: Manifests capture crawl context

## Corpus Directory Structure

### Snapshot-Based Layout

Each crawl creates a new snapshot in the following structure:

```
corpora/
├── {site_id}/
│   ├── {snapshot_id}/
│   │   ├── manifest.json
│   │   ├── markdown/
│   │   │   ├── api/
│   │   │   │   ├── 2/
│   │   │   │   │   └── overview.md
│   │   │   │   └── 3/
│   │   │   │       └── overview.md
│   │   │   └── index.md
│   │   ├── html/
│   │   │   └── ...
│   │   ├── json/
│   │   │   └── ...
│   │   └── chunks.jsonl (optional)
│   └── {another_snapshot_id}/
│       └── ...
└── {another_site_id}/
    └── ...
```

### Directory Components

- **`corpora/`**: Root directory for all corpus output
- **`{site_id}/`**: Site identifier from `SiteConfig.id`
- **`{snapshot_id}/`**: Timestamp-based snapshot identifier
- **`{format}/`**: Format-based directories (e.g., `markdown/`, `html/`, `json/`)
  - Each format directory preserves URL hierarchy as subdirectories
  - Root URLs (e.g., `https://example.com/`) are stored as `index.{ext}` in the format directory
  - URL paths (e.g., `/api/2/overview`) are stored as `api/2/overview.{ext}`
- **`manifest.json`**: Snapshot metadata and page index
- **`chunks.jsonl`**: Optional chunked content for LLM consumption

## Snapshot ID Generation

### Timestamp Format

Snapshot IDs use ISO 8601 format without separators:

```
YYYY-MM-DD_HHMM
```

**Example:** `2025-01-15_1430` (15 January 2025, 14:30 AEST)

### Timezone

Snapshot IDs use Australia/Brisbane timezone (UTC+10):

```python
from datetime import datetime
from zoneinfo import ZoneInfo

def new_snapshot_id() -> str:
    """Generate a new snapshot ID using current time in Australia/Brisbane."""
    now = datetime.now(ZoneInfo("Australia/Brisbane"))
    return now.strftime("%Y%m%dT%H%M%S")
```

### Uniqueness

Timestamp-based IDs ensure uniqueness (one snapshot per second). If multiple crawls occur in the same second, they create separate snapshots (no overwriting).

## Manifest Structure

### Manifest Location

Manifests are stored at `corpora/{site_id}/{snapshot_id}/manifest.json`

### Manifest Schema

```json
{
  "site_id": "example-site",
  "site_name": "Example Site",
  "provider": "crawl4ai",
  "snapshot_id": "2025-01-15_1430",
  "created_at": "2025-01-15T14:30:22+10:00",
  "entrypoints": [
    "https://example.com"
  ],
  "total_pages": 42,
  "formats": [
    "html",
    "markdown"
  ],
  "pages": [
    {
      "url": "https://example.com/api/2/overview",
      "title": "API Overview",
      "path": "markdown/api/2/overview.md",
      "formats": {
        "markdown": "markdown/api/2/overview.md",
        "html": "html/api/2/overview.html",
        "json": "json/api/2/overview.json"
      },
      "content_hash": "abc123def456..."
    }
  ]
}
```

### Manifest Fields

- **`site_id`**: Site identifier from `SiteConfig.id`
- **`site_name`**: Human-readable site name from `SiteConfig.name`
- **`provider`**: Scraper provider used (`crawl4ai`)
- **`snapshot_id`**: Snapshot identifier (timestamp)
- **`created_at`**: ISO 8601 timestamp of snapshot creation
- **`entrypoints`**: List of crawl entrypoints
- **`total_pages`**: Number of pages in snapshot
- **`formats`**: Content formats extracted
- **`pages`**: Array of page metadata objects

### Page Metadata

Each page entry in the manifest contains:

- **`url`**: Page URL
- **`title`**: Page title
- **`path`**: Relative path to primary page file (usually markdown, e.g., `markdown/api/2/overview.md`)
- **`formats`**: Dictionary mapping format names to file paths (e.g., `{"markdown": "markdown/api/2/overview.md", "html": "html/api/2/overview.html"}`)
- **`content_hash`**: SHA-256 hash of page content (for deduplication)

## Page File Naming

### Format-Based Directory Structure

Page files are organised by format first, then by URL hierarchy:

- **Format directories**: Each output format (markdown, html, json) has its own top-level directory
- **URL hierarchy**: URL paths are preserved as directory structure within each format directory
- **Root URLs**: Root URLs (`https://example.com/`) are stored as `index.{ext}` in the format directory
- **Path segments**: URL path segments become subdirectories (e.g., `/api/2/overview` → `api/2/overview.{ext}`)

**Examples:**
- `https://example.com/` → `markdown/index.md`
- `https://example.com/about` → `markdown/about.md`
- `https://example.com/api/2/overview` → `markdown/api/2/overview.md`
- `https://example.com/docs/user/guide` → `markdown/docs/user/guide.md`

### Path Generation

Paths are generated from URL structure:

```python
def _url_to_path_structure(url: str) -> tuple[Path, str]:
    """Convert URL to directory path structure preserving hierarchy."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    
    if not path:
        return Path("."), "index"
    
    # Split path into segments and sanitise each
    path_parts = path.split("/")
    sanitised_parts = [sanitise_segment(part) for part in path_parts]
    
    # Last part is filename, rest is directory structure
    filename = sanitised_parts[-1] or "index"
    dir_parts = sanitised_parts[:-1] if len(sanitised_parts) > 1 else []
    
    return Path(*dir_parts) if dir_parts else Path("."), filename
```

### Collision Handling

If multiple pages would create the same file path (e.g., different query parameters), a numeric suffix is added:
- First occurrence: `api/2/overview.md`
- Collision: `api/2/overview-1.md`

### File Extensions

File extensions match content formats:

- `html` → `.html`
- `markdown` → `.md`
- Multiple formats create multiple files (if supported)

## Chunking Output

### JSONL Format

Chunked content is written to `chunks.jsonl` in JSONL format (one JSON object per line):

```jsonl
{"url": "https://example.com/page", "title": "Page Title", "chunk_index": 0, "content": "Chunk content..."}
{"url": "https://example.com/page", "title": "Page Title", "chunk_index": 1, "content": "Next chunk..."}
```

### Chunk Metadata

Each chunk contains:

- **`url`**: Source page URL
- **`title`**: Source page title
- **`chunk_index`**: Zero-based chunk index within page
- **`content`**: Chunk text content

## Downstream Consumer Integration

### Reading Snapshots

1. List snapshots: `corpora/{site_id}/` directories
2. Read manifest: `corpora/{site_id}/{snapshot_id}/manifest.json`
3. Load pages: Read files from format directories (e.g., `markdown/`, `html/`) using manifest paths
4. Process chunks: Read `chunks.jsonl` line by line

### Example Integration

```python
import json
from pathlib import Path

def load_snapshot(site_id: str, snapshot_id: str) -> dict:
    """Load snapshot manifest and return metadata."""
    manifest_path = Path(f"corpora/{site_id}/{snapshot_id}/manifest.json")
    with manifest_path.open() as f:
        return json.load(f)

def load_chunks(site_id: str, snapshot_id: str) -> list[dict]:
    """Load chunked content from JSONL file."""
    chunks_path = Path(f"corpora/{site_id}/{snapshot_id}/chunks.jsonl")
    chunks = []
    with chunks_path.open() as f:
        for line in f:
            chunks.append(json.loads(line))
    return chunks
```

## Best Practices

1. **Snapshot Isolation**: Each crawl creates a new snapshot (no overwriting)
2. **Manifest First**: Always create manifest before writing pages
3. **Atomic Writes**: Write manifest to temp file, then rename
4. **Safe Filenames**: Use filesystem-safe slugs for page files
5. **Content Hashing**: Include content hashes for deduplication
6. **Metadata Preservation**: Capture all crawl context in manifest

## References

- `.cursor/rules/50-corpus-layout-patterns-web-scraper.mdc` - Corpus layout requirements
- `.cursor/rules/20-development-environment-web-scraper.mdc` - Directory structure requirements
