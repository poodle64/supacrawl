# Creating Site Configurations

This guide explains how to create and manage site configurations for web-scraper.

## Overview

Site configurations define crawl parameters in YAML files stored in the `sites/` directory. Each configuration specifies:

- Site identification (id, name)
- Crawl parameters (entrypoints, include/exclude patterns, limits)
- Content extraction options (formats, main content only)

## Configuration Schema

### Required Fields

All site configurations must include these fields:

```yaml
id: example-site              # Unique site identifier (matches filename)
name: Example Site            # Human-readable site name
entrypoints:                 # Starting URLs (at least one required)
  - https://example.com
include:                     # URL patterns to include
  - https://example.com/**
exclude:                     # URL patterns to exclude
  - https://example.com/admin/**
max_pages: 100               # Maximum pages to crawl (positive integer)
formats:                     # Content formats to extract
  - html
only_main_content: true      # Extract main content only (boolean)
include_subdomains: false   # Include subdomains (boolean)
```

## Step-by-Step Guide

### Step 1: Choose Site Identifier

Choose a unique site identifier using kebab-case:

- ✅ `example-site`
- ✅ `my-blog`
- ✅ `documentation-site`
- ❌ `example_site` (use hyphens, not underscores)
- ❌ `ExampleSite` (use lowercase)

### Step 2: Create YAML File

Create a new file in `sites/` directory:

```bash
touch sites/example-site.yaml
```

**Important**: Filename (without `.yaml`) must match the `id` field.

### Step 3: Define Basic Configuration

Start with minimal required fields:

```yaml
id: example-site
name: Example Site
provider: crawl4ai
entrypoints:
  - https://example.com
include:
  - https://example.com/**
exclude: []
max_pages: 50
formats:
  - html
only_main_content: true
include_subdomains: false
```

### Step 4: Configure Entrypoints

Add starting URLs for the crawl:

```yaml
entrypoints:
  - https://example.com
  - https://example.com/blog
  - https://example.com/docs
```

**Note**: At least one entrypoint is required.

### Step 5: Configure Include/Exclude Patterns

Define URL patterns to include and exclude:

```yaml
include:
  - https://example.com/**
  - https://example.com/blog/**
exclude:
  - https://example.com/admin/**
  - https://example.com/private/**
```

Pattern syntax: Crawl4AI supports regex patterns (check Crawl4AI docs)

### Step 6: Set Limits

Configure crawl limits:

```yaml
max_pages: 100  # Maximum pages to crawl
```

**Tip**: Start with smaller limits (50-100) for testing, increase for production crawls.

### Step 7: Choose Formats

Select content formats to extract:

```yaml
formats:
  - html        # HTML content
  - markdown    # Markdown content (if supported by provider)
```

**Note**: Available formats depend on Crawl4AI capabilities.

### Step 8: Configure Content Extraction

Set content extraction options:

```yaml
only_main_content: true      # Extract main content only (removes navigation, headers, footers)
include_subdomains: false   # Include subdomains in crawl
```

### Step 9: Configure Markdown Fixes (Optional)

Control markdown fix plugins that address issues in upstream tools:

```yaml
# Enable all markdown fixes
markdown_fixes:
  enabled: true

# Or enable specific fixes only
markdown_fixes:
  enabled: true
  fixes:
    missing-link-text-in-lists: true
```

**When to use**: Enable fixes when you need workarounds for issues in upstream tools (like Crawl4AI). See `docs/40-usage/markdown-fixes.md` for details.

**Default**: All fixes are **disabled by default**. Omit this section to disable all fixes.

**See Template**: For a complete example of all available configuration options, see `sites/template.yaml`.

## Common Configuration Patterns

### Simple Blog

```yaml
id: my-blog
name: My Blog
provider: crawl4ai
entrypoints:
  - https://myblog.com
include:
  - https://myblog.com/**
exclude:
  - https://myblog.com/admin/**
max_pages: 200
formats:
  - html
only_main_content: true
include_subdomains: false
```

### Documentation Site

```yaml
id: docs-site
name: Documentation Site
provider: crawl4ai
entrypoints:
  - https://docs.example.com
include:
  - https://docs.example.com/**
exclude:
  - https://docs.example.com/search/**
max_pages: 500
formats:
  - html
  - markdown
only_main_content: true
include_subdomains: false
```

### Multi-Subdomain Site

```yaml
id: multi-subdomain-site
name: Multi-Subdomain Site
provider: crawl4ai
entrypoints:
  - https://example.com
include:
  - https://*.example.com/**
exclude: []
max_pages: 300
formats:
  - html
only_main_content: true
include_subdomains: true
```

## Validation and Testing

### Validate Configuration

Test configuration loading:

```bash
web-scraper show-site example-site
```

This command validates the configuration and displays a summary.

### Common Validation Errors

**Empty Entrypoints:**
```
Error: At least one entrypoint is required. [correlation_id=abc12345]
```

**Invalid Max Pages:**
```
Error: max_pages must be greater than 0. [correlation_id=abc12345]
```


### Test Crawl

Run a test crawl with limited pages:

```yaml
max_pages: 5  # Start with small limit for testing
```

```bash
web-scraper crawl example-site
```

Check corpus output:

```bash
ls corpora/example-site/
# Should show snapshot directory
```

## Best Practices

1. **Descriptive IDs**: Use kebab-case IDs that identify the site
2. **Consistent Naming**: Match filename to `id` field exactly
3. **Reasonable Limits**: Set `max_pages` based on site size
4. **Pattern Precision**: Use specific include/exclude patterns
5. **Format Selection**: Choose formats based on downstream needs
6. **Version Control**: Track configuration changes in git
7. **Test First**: Validate configurations before production crawls

## Troubleshooting

### Configuration Not Found

**Error:** `Site configuration not found: sites/example-site.yaml`

**Solution:** 
- Check filename matches `id` field
- Verify file is in `sites/` directory
- Check file has `.yaml` extension

### Validation Errors

**Error:** `Invalid site configuration: ...`

**Solution:**
- Check all required fields are present
- Verify field types match schema (strings, integers, booleans, lists)
- Check YAML syntax (indentation, colons, dashes)

### Crawler Errors

**Error:** `Failed to crawl site using Crawl4AI`

**Solution:**
- Check Crawl4AI installation (`crawl4ai-doctor`)
- Review error messages in logs

## References

- `docs/30-architecture/site-configuration-web-scraper.md` - Site configuration system overview
- `.cursor/rules/50-site-config-patterns-web-scraper.mdc` - Configuration pattern requirements
- `sites/example_site.yaml` - Example configuration file
