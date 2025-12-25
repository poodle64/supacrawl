# Site Configuration System

## Why Site Configuration Exists

The site configuration system allows users to define crawl parameters declaratively in YAML files, enabling:

- **Separation of concerns**: Configuration separate from code
- **Reproducibility**: Same configuration produces same results
- **Version control**: Track configuration changes over time
- **Reusability**: Share configurations across environments

## Site Configuration Schema

### SiteConfig Model

Site configurations are validated against the `SiteConfig` Pydantic model:

```python
class SiteConfig(BaseModel):
    """Model representing a site configuration."""

    id: str
    name: str
    entrypoints: list[str]
    include: list[str]
    exclude: list[str]
    max_pages: int
    formats: list[str]
    only_main_content: bool
    include_subdomains: bool
    sitemap: SitemapConfigModel       # Optional: sitemap-based URL discovery
    robots: RobotsConfigModel         # Optional: robots.txt compliance
    politeness: CrawlPolitenessConfig # Optional: crawl pacing
```

### Required Fields

- **`id`**: Unique site identifier (matches filename without `.yaml`)
- **`name`**: Human-readable site name
- **`entrypoints`**: List of starting URLs (at least one required)
- **`include`**: URL patterns to include in crawl
- **`exclude`**: URL patterns to exclude from crawl
- **`max_pages`**: Maximum pages to crawl (positive integer)
- **`formats`**: Content formats to extract (`html`, `markdown`)
- **`only_main_content`**: Extract main content only (boolean)
- **`include_subdomains`**: Include subdomains in crawl (boolean)

## Configuration File Structure

### File Location

Site configurations must be stored in the `sites/` directory:

```
sites/
├── example-site.yaml
├── meta.yaml
└── another-site.yaml
```

### File Naming

- Use kebab-case for filenames: `example-site.yaml`
- Filename (without `.yaml`) must match `id` field in configuration
- Use descriptive names that identify the site

### YAML Format

Use standard YAML syntax with consistent indentation:

```yaml
id: example-site
name: Example Site
entrypoints:
  - https://example.com
include:
  - https://example.com/**
exclude:
  - https://example.com/admin/**
max_pages: 100
formats:
  - html
  - markdown
only_main_content: true
include_subdomains: false
```

## Validation Rules

### Entrypoints Validation

- At least one entrypoint URL is required
- URLs must be valid HTTP/HTTPS URLs
- Empty entrypoints list raises `ValidationError`

**Example error:**
```python
ValidationError(
    "At least one entrypoint is required.",
    field="entrypoints",
    value=[],
    correlation_id="abc12345",
    context={"example": "entrypoints: ['https://example.com']"},
)
```

### Max Pages Validation

- Must be positive integer (greater than 0)
- Zero or negative values raise `ValidationError`

**Example error:**
```python
ValidationError(
    "max_pages must be greater than 0.",
    field="max_pages",
    value=0,
    correlation_id="abc12345",
)
```


## Configuration Loading

### Loading Process

1. Read YAML file from `sites/` directory
2. Parse YAML content
3. Validate against `SiteConfig` model (Pydantic validation)
4. Return `SiteConfig` instance or raise `ConfigurationError`

### Error Handling

**File Not Found:**
```python
ConfigurationError(
    f"Site configuration not found: {config_path}",
    config_path=str(config_path),
    correlation_id="abc12345",
)
```

**Invalid Configuration:**
```python
ConfigurationError(
    f"Invalid site configuration: {validation_error}",
    config_path=str(config_path),
    correlation_id="abc12345",
    context={"validation_errors": validation_errors},
)
```

## Common Configuration Patterns

### Simple Site

```yaml
id: simple-site
name: Simple Site
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

### Multi-Entrypoint Site

```yaml
id: multi-entrypoint-site
name: Multi-Entrypoint Site
entrypoints:
  - https://example.com
  - https://example.com/blog
  - https://example.com/docs
include:
  - https://example.com/**
exclude:
  - https://example.com/admin/**
max_pages: 200
formats:
  - html
only_main_content: true
include_subdomains: false
```

### Subdomain-Inclusive Site

```yaml
id: subdomain-site
name: Subdomain Site
entrypoints:
  - https://example.com
include:
  - https://*.example.com/**
exclude: []
max_pages: 100
formats:
  - html
  - markdown
only_main_content: true
include_subdomains: true
```

## Best Practices

1. **Descriptive IDs**: Use kebab-case IDs that identify the site
2. **Consistent Naming**: Match filename to `id` field
3. **Reasonable Limits**: Set `max_pages` based on site size
4. **Pattern Precision**: Use specific include/exclude patterns
5. **Format Selection**: Choose formats based on downstream needs
6. **Version Control**: Track configuration changes in git

## References

- `.cursor/rules/50-site-config-patterns-supacrawl.mdc` - Configuration pattern requirements
- `.cursor/rules/70-error-handling-supacrawl.mdc` - Configuration error handling
- `docs/40-usage/creating-site-configs-supacrawl.md` - Configuration creation guide
