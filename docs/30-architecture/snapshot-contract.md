# Snapshot Contract

## Purpose

A snapshot is a self-contained, timestamped corpus of scraped pages from a website. Each snapshot includes all page content in requested formats, metadata, and a manifest that describes the snapshot structure.

## Directory Layout

Snapshots are stored in a hierarchical directory structure:

```
corpora/
  {site_id}/
    latest/               (symlink to most recent snapshot)
    {snapshot_id}/
      manifest.json
      .meta/              (internal artefacts)
        crawl_state.json
        checksums.sha256
        run.log.jsonl
      {format}/
        {url_hierarchy}/
          {filename}.{ext}
      chunks.jsonl        (optional)
```

**Components:**
- `site_id`: Site configuration identifier (from `SiteConfig.id`)
- `latest`: Symlink to most recent snapshot (always points to current data)
- `snapshot_id`: Timestamp-based identifier (format: `YYYY-MM-DD_HHMM`, timezone: Australia/Brisbane)
- `.meta`: Internal directory for crawl state, checksums, and logs
- `format`: Output format directory (`markdown`, `html`, `text`, `json`)
- `url_hierarchy`: Directory structure preserving URL path hierarchy
- `filename`: Filesystem-safe filename derived from URL
- `chunks.jsonl`: Optional chunked output for LLM consumption

## Manifest Structure

The `manifest.json` file is the authoritative description of a snapshot. It contains:

### Required Fields

- `site_id` (string): Site configuration identifier
- `site_name` (string): Human-readable site name
- `snapshot_id` (string): Unique snapshot identifier
- `created_at` (string): ISO-8601 timestamp when snapshot was created
- `provider` (string): Crawler provider name (e.g., `"playwright"`)
- `entrypoints` (array[string]): List of entrypoint URLs used for crawling
- `total_pages` (integer): Total number of pages in snapshot
- `formats` (array[string]): List of output formats produced (`"markdown"`, `"html"`, `"text"`, `"json"`)
- `pages` (array[object]): Array of page metadata entries
- `correlation_id` (string): Correlation ID for request tracking
- `metadata` (object): Snapshot metadata (see Metadata Fields)

### Optional Fields

- `status` (string): Snapshot status (`"in_progress"`, `"completed"`, `"aborted"`)
- `crawl_settings` (object): Crawl configuration summary
- `stats` (object): Aggregated statistics (present when completed)
- `boilerplate_hashes` (array[object]): Boilerplate content hashes
- `error` (string): Error message if snapshot creation failed

### Page Entry Structure

Each entry in `pages[]` contains:

- `url` (string): Page URL
- `title` (string): Page title
- `content_hash` (string): SHA-256 hash of page content
- `path` (string): Primary file path relative to snapshot root
- `formats` (object): Map of format name to file path (relative to snapshot root)

**Example:**
```json
{
  "url": "https://example.com/page",
  "title": "Page Title",
  "content_hash": "abc123...",
  "path": "markdown/page.md",
  "formats": {
    "markdown": "markdown/page.md",
    "html": "html/page.html",
    "json": "json/page.json"
  }
}
```

## Metadata Fields

The `metadata` object provides provenance and reproducibility information:

- `snapshot_id` (string): Snapshot identifier
- `site_id` (string): Site configuration identifier
- `created_at` (string): UTC ISO-8601 timestamp when snapshot was created
- `git_commit` (string | null): Git commit hash (7 characters) or null if unavailable
- `site_config_hash` (string): SHA-256 hash of site configuration (64 hex characters)
- `crawl_engine` (string): Crawler engine name (e.g., `"playwright"`)
- `crawl_engine_version` (string | null): Crawler engine version or null if unavailable
- `schema_version` (string): Manifest schema version (e.g., `"1.0"`)

## Supported Formats

- `markdown`: Markdown format with YAML frontmatter
- `html`: HTML format
- `text`: Plain text format
- `json`: JSON format

All formats are written to format-specific directories under the snapshot root.

## Schema Versioning

The `metadata.schema_version` field indicates the manifest schema version. This enables:

- **Forward compatibility**: Consumers can detect schema versions they support
- **Validation**: Machine-readable schema validation (see `schemas/snapshot-manifest.schema.json`)
- **Evolution**: Future schema changes can be versioned

**Current version:** `1.0`

**Versioning rules:**
- Schema versions follow semantic versioning (major.minor)
- Major version increments indicate breaking changes
- Minor version increments indicate additive changes
- Older snapshots without `schema_version` are treated as pre-1.0

## Stability Guarantees

### Stable Fields

The following fields are guaranteed to remain stable across schema versions:

- `site_id`, `site_name`, `snapshot_id`, `created_at`
- `provider`, `entrypoints`, `total_pages`, `formats`
- `pages[].url`, `pages[].title`, `pages[].content_hash`
- `pages[].path`, `pages[].formats`
- `metadata.snapshot_id`, `metadata.site_id`, `metadata.created_at`
- `metadata.site_config_hash`, `metadata.crawl_engine`, `metadata.schema_version`

### Backward Compatibility

- Older snapshots without `metadata.schema_version` must load without error
- Optional fields may be added in future versions
- Required fields will not be removed without a major version increment

### Forward Compatibility

- Consumers should ignore unknown fields
- Consumers should handle missing optional fields gracefully
- Schema validation should use `metadata.schema_version` to select appropriate validator
