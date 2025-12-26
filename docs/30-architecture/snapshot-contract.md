# Crawl Output Contract

## Purpose

The `crawl` command produces a directory of markdown files from a website crawl. This document describes the output format.

## Directory Layout

Crawl output is stored in a flat directory structure:

```
output_dir/
  manifest.json     # Tracks scraped URLs for resume
  index.md          # Root page (if crawled)
  about.md          # Other pages
  docs_guide.md     # URL paths become filenames
  docs_guide_a1b2.md  # Hash suffix for duplicate names
```

**Components:**
- `manifest.json`: Simple manifest for resume support
- `*.md`: Markdown files with YAML frontmatter

## Manifest Structure

The `manifest.json` file tracks crawled URLs for resume functionality:

```json
{
  "scraped_urls": [
    "https://example.com/",
    "https://example.com/about",
    "https://example.com/docs/guide"
  ]
}
```

**Fields:**
- `scraped_urls` (array[string]): List of URLs that have been scraped

## Markdown File Format

Each scraped page is saved as a markdown file with YAML frontmatter:

```markdown
---
source_url: https://example.com/about
title: About Us
description: Learn about our company
---

# About Us

Page content in markdown format...
```

**Frontmatter fields:**
- `source_url` (string): Original URL
- `title` (string): Page title
- `description` (string, optional): Page meta description

## Filename Generation

Filenames are derived from URL paths:

1. URL path is converted to filesystem-safe name
2. Slashes become underscores
3. Special characters are removed
4. Duplicate names get hash suffix

**Examples:**
- `/` → `index.md`
- `/about` → `about.md`
- `/docs/guide` → `docs_guide.md`
- `/docs/guide` (duplicate) → `docs_guide_a1b2c3d4.md`

## Resume Support

Use `--resume` to continue an interrupted crawl:

```bash
supacrawl crawl https://example.com --output corpus/ --resume
```

The crawler reads `manifest.json` and skips already-scraped URLs.

## Output Formats

The `--format` option controls output format:

- `markdown` (default): Markdown with frontmatter
- `html`: Raw HTML content
- `json`: JSON with all metadata

Multiple formats can be requested:

```bash
supacrawl crawl https://example.com --output corpus/ --format markdown --format html
```
