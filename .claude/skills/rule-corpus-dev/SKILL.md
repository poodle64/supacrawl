---
name: rule-corpus-dev
description: Corpus management with snapshot layout, manifest generation, compression,
  and chunking
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Corpus management with snapshot layout, manifest generation, compression, and chunking

This skill is auto-generated from cursor rules. Follow these development standards:

# Source: 50-corpus-layout-patterns-supacrawl.mdc

# Corpus Layout Patterns

## Core Principles

All corpus snapshots must follow consistent directory structure and manifest format for downstream consumer compatibility.

## Mandatory Requirements

### Directory Structure

- ✅ **Must** use snapshot-based layout: `corpora/{site_id}/{snapshot_id}/`
- ✅ **Must** use site ID from `SiteConfig.id` as directory name
- ✅ **Must** use timestamp-based snapshot IDs (ISO 8601 format: `YYYYMMDDTHHMMSS`)
- ✅ **Must** create `pages/` subdirectory for page content files
- ✅ **Must** create `manifest.json` at snapshot root
- ✅ **Must** create snapshot directory if it doesn't exist
- ❌ **Must NOT** overwrite existing snapshots (each crawl creates new snapshot)

### Snapshot ID Generation

- ✅ **Must** use `new_snapshot_id()` function to generate snapshot IDs
- ✅ **Must** use current time in Australia/Brisbane timezone
- ✅ **Must** use ISO 8601 format without separators: `YYYYMMDDTHHMMSS`
- ✅ **Must** ensure snapshot IDs are unique (timestamp-based prevents collisions)
- ✅ **Must** use snapshot ID as directory name (exact match)

**Example:** `20250115T143022` (15 January 2025, 14:30:22 AEST)

### Manifest Structure

- ✅ **Must** create `manifest.json` at snapshot root
- ✅ **Must** include site metadata: `site_id`, `site_name`, `provider`, `snapshot_id`, `created_at`
- ✅ **Must** include crawl metadata: `entrypoints`, `total_pages`, `formats`
- ✅ **Must** include pages array with page metadata: `url`, `title`, `path`, `content_hash`
- ✅ **Must** use JSON format for manifest
- ✅ **Must** write manifest atomically (write to temp file, then rename)

**Manifest structure:**
```json
{
  "site_id": "example-site",
  "site_name": "Example Site",
  "provider": "playwright",
  "snapshot_id": "20250115T143022",
  "created_at": "2025-01-15T14:30:22+10:00",
  "entrypoints": ["https://example.com"],
  "total_pages": 42,
  "formats": ["html", "markdown"],
  "pages": [
    {
      "url": "https://example.com/page",
      "title": "Page Title",
      "path": "pages/0001-page.html",
      "content_hash": "abc123..."
    }
  ]
}
```

### Page File Naming

- ✅ **Must** use filesystem-safe slugs for page filenames
- ✅ **Must** prefix filenames with zero-padded index (e.g., `0001-`, `0002-`)
- ✅ **Must** sanitise URLs to create safe filenames (replace `/` with `_`, spaces with `-`)
- ✅ **Must** preserve file extensions from formats (`.html`, `.md`)
- ✅ **Must** store pages in `pages/` subdirectory

**Example:** `pages/0001-example-page.html`

### Chunking Output

- ✅ **May** create chunked output in JSONL format
- ✅ **Must** use `chunk_snapshot()` function for chunking
- ✅ **Must** write chunks to `chunks.jsonl` in snapshot directory
- ✅ **Must** include chunk metadata: `url`, `title`, `chunk_index`, `content`
- ✅ **Must** use one JSON object per line (JSONL format)

## Key Directives

- **Snapshot-based**: Each crawl creates new timestamped snapshot
- **Consistent structure**: Follow `corpora/{site_id}/{snapshot_id}/` pattern
- **Manifest required**: Always create `manifest.json` with metadata
- **Safe filenames**: Use filesystem-safe slugs for page files

## References

- `.cursor/rules/20-development-environment-supacrawl.mdc` - Directory structure requirements
- `docs/30-architecture/corpus-layout-supacrawl.md` - Detailed corpus layout documentation

---

# Source: 50-site-config-patterns-supacrawl.mdc

# Site Configuration Patterns

## Core Principles

All site configurations must follow the `SiteConfig` Pydantic model schema and be stored as YAML files in the `sites/` directory.

## Mandatory Requirements

### Configuration File Structure

- ✅ **Must** use YAML format for site configurations
- ✅ **Must** store configurations in `sites/` directory
- ✅ **Must** use filename (without `.yaml`) as site identifier
- ✅ **Must** follow `SiteConfig` model schema exactly
- ✅ **Must** validate configurations on load (Pydantic validation)
- ❌ **Must NOT** use JSON or other formats for site configurations
- ❌ **Must NOT** store configurations outside `sites/` directory

### SiteConfig Model Schema

- ✅ **Must** include all required fields: `id`, `name`, `entrypoints`, `include`, `exclude`, `max_pages`, `formats`, `only_main_content`, `include_subdomains`
- ✅ **Must** use `id` field as unique site identifier (matches filename)
- ✅ **Must** use `name` field for human-readable site name
- ✅ **Must** provide at least one entrypoint URL in `entrypoints` list
- ✅ **Must** use `include` patterns for URLs to include in crawl
- ✅ **Must** use `exclude` patterns for URLs to exclude from crawl
- ✅ **Must** set `max_pages` to positive integer (limits crawl size)
- ✅ **Must** specify `formats` list (e.g., `["html", "markdown"]`)
- ✅ **Must** set `only_main_content` boolean (extract main content only)
- ✅ **Must** set `include_subdomains` boolean (include subdomains in crawl)

### Validation Rules

- ✅ **Must** validate `entrypoints` list is not empty (at least one URL required)
- ✅ **Must** validate `max_pages` is positive integer (greater than 0)
- ✅ **Must** validate URLs in `entrypoints` are valid URLs
- ✅ **Must** raise `ValidationError` with field context when validation fails
- ✅ **Must** include correlation ID in validation errors

**Example validation:**
```python
@field_validator("entrypoints")
@classmethod
def validate_entrypoints(cls, value: list[str]) -> list[str]:
    """Ensure at least one entrypoint is provided."""
    if not value:
        correlation_id = generate_correlation_id()
        raise ValidationError(
            "At least one entrypoint is required.",
            field="entrypoints",
            value=value,
            correlation_id=correlation_id,
            context={"example": "entrypoints: ['https://example.com']"},
        )
    return value
```

### Configuration Loading

- ✅ **Must** use `load_site_config()` function to load configurations
- ✅ **Must** handle `FileNotFoundError` when configuration file doesn't exist
- ✅ **Must** handle `ValidationError` when configuration is invalid
- ✅ **Must** raise `ConfigurationError` with config path context on load failure
- ✅ **Must** validate configuration immediately on load (don't defer validation)

### Configuration Naming

- ✅ **Must** use kebab-case for site IDs (e.g., `example-site`)
- ✅ **Must** use descriptive names that identify the site
- ✅ **Must** match filename to site ID (e.g., `example-site.yaml` → `id: example-site`)

## Key Directives

- **YAML format**: Always use YAML for site configurations
- **Schema compliance**: Follow `SiteConfig` model exactly
- **Validation**: Validate on load, provide helpful error messages
- **Naming**: Use kebab-case, match filename to site ID

## References

- `.cursor/rules/master/70-input-validation-basics.mdc` - Universal input validation requirements
- `.cursor/rules/70-error-handling-supacrawl.mdc` - Configuration error handling patterns
- `docs/40-usage/creating-site-configs-supacrawl.md` - Site configuration guide and examples

---
*Generated: 2025-12-22 21:05:15 UTC*
*Source rules: 50-corpus-layout-patterns-supacrawl.mdc, 50-site-config-patterns-supacrawl.mdc*
