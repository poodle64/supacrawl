# Plan: Unified CLI with Optional Config Files

## Vision

Make URL the primary input, with options as CLI flags. Config files become optional "saved presets" rather than required configuration.

---

## Current State

```bash
# URL-based (Firecrawl-style) - limited options
web-scraper scrape-url https://example.com
web-scraper map-url https://example.com --limit 50
web-scraper crawl-url https://example.com --limit 100 --output corpus/

# Config-based (current primary workflow) - full options
web-scraper crawl sharesight  # requires sites/sharesight.yaml
```

**Problem:** The URL commands have fewer options than the config-based commands. Users who want include/exclude patterns, politeness settings, etc. must create a YAML file.

---

## Proposed State

### Primary Commands (URL-first)

```bash
# Scrape single URL
web-scraper scrape https://example.com
web-scraper scrape https://example.com --format markdown,html --wait 2000

# Map (discover URLs)
web-scraper map https://example.com
web-scraper map https://example.com --limit 200 --depth 3 --sitemap include

# Crawl (map + scrape)
web-scraper crawl https://example.com
web-scraper crawl https://example.com \
  --limit 100 \
  --depth 3 \
  --include "*/docs/*" \
  --exclude "*/blog/*" \
  --output corpus/example/

# Batch scrape (multiple URLs)
web-scraper batch urls.txt --concurrency 5 --output results/
cat urls.txt | web-scraper batch - --output results/
```

### Full Option Parity

All options available in YAML should be available as CLI flags:

```bash
web-scraper crawl https://api.sharesight.com/api/v3 \
  --limit 500 \
  --include "https://api.sharesight.com/api/v3/**" \
  --exclude "*/admin/*" \
  --exclude "*/legacy/*" \
  --only-main-content \
  --format markdown,html \
  --concurrency 3 \
  --delay 2.0 \
  --timeout 120 \
  --output corpus/sharesight/
```

### Optional: Save as Config

```bash
# Save current options as a reusable config
web-scraper crawl https://api.sharesight.com/api/v3 \
  --limit 500 \
  --include "https://api.sharesight.com/api/v3/**" \
  --save-config sharesight

# Creates sites/sharesight.yaml with these settings
# Now you can reuse:
web-scraper crawl --config sharesight
# or
web-scraper crawl sharesight  # if we keep this shorthand
```

### Config as Override

```bash
# Use config but override specific options
web-scraper crawl --config sharesight --limit 50 --fresh
```

---

## Command Naming Options

### Option A: Keep Current Names (add options)
```bash
web-scraper scrape-url URL [OPTIONS]
web-scraper map-url URL [OPTIONS]
web-scraper crawl-url URL [OPTIONS]
web-scraper crawl CONFIG [OPTIONS]   # existing config-based
```
**Pro:** Backwards compatible
**Con:** Confusing that `crawl` and `crawl-url` are different

### Option B: Unified Commands
```bash
web-scraper scrape URL [OPTIONS]
web-scraper map URL [OPTIONS]
web-scraper crawl URL [OPTIONS]
web-scraper crawl --config NAME [OPTIONS]  # config mode via flag
```
**Pro:** Cleaner, matches Firecrawl
**Con:** Breaking change for existing `crawl` command

### Option C: Hybrid
```bash
web-scraper scrape URL [OPTIONS]      # URL-first (new)
web-scraper map URL [OPTIONS]         # URL-first (new)
web-scraper crawl URL [OPTIONS]       # URL-first (new)
web-scraper site crawl NAME [OPTIONS] # config-based (renamed)
web-scraper site list                 # list configs
web-scraper site show NAME            # show config
```
**Pro:** Clear separation, no ambiguity
**Con:** More commands to learn

---

## Recommended Approach: Option B

Unify on Firecrawl-style commands where URL is the argument:

```bash
web-scraper scrape URL [OPTIONS]
web-scraper map URL [OPTIONS]
web-scraper crawl URL [OPTIONS]
```

Config files become a `--config` flag:
```bash
web-scraper crawl --config sharesight
web-scraper crawl https://example.com --config sharesight --limit 50
```

---

## Implementation Steps

### Phase 1: Add Missing CLI Options
Add to `crawl-url` (or new `crawl`):
- `--include` (multiple)
- `--exclude` (multiple)
- `--only-main-content / --no-only-main-content`
- `--format` (multiple: markdown, html, text)
- `--concurrency`
- `--delay`
- `--timeout`
- `--sitemap` (include/skip/only)
- `--include-subdomains`

### Phase 2: Rename Commands
- `scrape-url` → `scrape`
- `map-url` → `map`
- `crawl-url` → `crawl`
- Deprecate old names (keep as aliases with warning)

### Phase 3: Add Config Flag
- `--config NAME` loads from sites/NAME.yaml
- CLI flags override config values
- `--save-config NAME` saves current options

### Phase 4: Deprecate Old Workflow
- `web-scraper crawl NAME` becomes `web-scraper crawl --config NAME`
- Keep old syntax as alias with deprecation warning
- Remove in next major version

---

## Output Structure

For URL-based crawls without `--output`, where does output go?

**Option 1: Auto-generate from URL**
```bash
web-scraper crawl https://api.sharesight.com/api/v3
# → corpus/api-sharesight-com/2025-01-15_1430/
```

**Option 2: Require --output**
```bash
web-scraper crawl https://example.com --output corpus/example/
```

**Option 3: Current directory by default**
```bash
web-scraper crawl https://example.com
# → ./crawl-output/
```

**Recommendation:** Option 1 - derive from URL, but allow `--output` override.

---

## Migration Path

1. **v2.x:** Add new commands alongside old ones
   - `scrape` as alias for `scrape-url`
   - `map` as alias for `map-url`
   - New unified `crawl` that accepts URL or `--config`
   - Old `crawl NAME` still works

2. **v3.0:** Remove deprecated commands
   - Only new unified commands
   - `--config` for saved configurations

---

## Questions to Resolve

1. **Output location for URL-based crawls?** Auto-generate from URL vs require explicit?

2. **Keep `sites/` directory?** Or move to `~/.config/web-scraper/sites/`?

3. **Snapshot versioning for URL-based?** Current system uses site ID - what for ad-hoc URLs?

4. **Resume support?** How does `--resume` work without a config file?

---

## Example: Before and After

### Before (Current)
```yaml
# sites/sharesight.yaml
name: Sharesight API
entrypoints:
  - https://api.sharesight.com/api/v3
include:
  - https://api.sharesight.com/api/v3/**
exclude: []
max_pages: 500
formats:
  - markdown
  - html
only_main_content: true
```

```bash
web-scraper crawl sharesight
```

### After (Proposed)
```bash
# One-liner equivalent
web-scraper crawl https://api.sharesight.com/api/v3 \
  --limit 500 \
  --include "https://api.sharesight.com/api/v3/**" \
  --format markdown,html \
  --only-main-content

# Or save for reuse
web-scraper crawl https://api.sharesight.com/api/v3 \
  --limit 500 \
  --include "https://api.sharesight.com/api/v3/**" \
  --save-config sharesight

# Then reuse
web-scraper crawl --config sharesight
```
