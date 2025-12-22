# Web-Scraper Roadmap: Path to Firecrawl Output Parity

**Goal**: Achieve full output format compatibility with Firecrawl markdown while maintaining unique local-first features.

**Current Status**: 99.6% similarity on prose content, 1 critical bug blocking full parity

---

## Phase 1: Critical Bug Fixes (P0 - Blocker)

**Goal**: Fix link preservation bug to achieve 95%+ similarity across all page types

### 1.1 Fix Table Link Preservation

**Issue**: Links in table cells are lost during markdown conversion (100% link loss)

**Evidence**: IANA Reserved Domains page - 11/11 A-label links missing

**Root Cause Analysis**:
1. Test if Crawl4AI `DefaultMarkdownGenerator` strips links
2. Test if `PruningContentFilter` removes links incorrectly
3. Test if `markdown_fixes` plugins interfere

**Debug Steps**:
```bash
# Test 1: Disable content filtering
# In site config: only_main_content: false

# Test 2: Disable markdown fixes
# In site config: markdown_fixes.enabled: false

# Test 3: Inspect raw HTML vs markdown
# Compare result.html with result.markdown from Crawl4AI
```

**Solution Paths**:
- **Option A**: Fix upstream in Crawl4AI (if bug confirmed there)
- **Option B**: Custom markdown post-processor to restore links from HTML
- **Option C**: Alternative markdown generator (e.g., html2text with custom config)

**Acceptance Criteria**:
- [ ] IANA Reserved Domains: 11/11 A-label links preserved
- [ ] Table link preservation test passes
- [ ] No regression on prose content quality (maintain 99.6%)

**Timeline**: Priority fix - investigate and implement within 1 week

**Files to Modify**:
- `web_scraper/scrapers/crawl4ai.py` (if custom post-processor)
- `web_scraper/content/fixes.py` (if fix via plugin)
- `tests/e2e/test_table_link_preservation.py` (new test)

---

### 1.2 Add Link Preservation Tests

**Purpose**: Prevent regression of link preservation bug

**Test Cases**:
1. **Table links**: IANA Reserved Domains (11 links in IDN table)
2. **Inline links**: GitHub README (navigation links)
3. **Reference links**: Wikipedia article (footnote links)
4. **Image links**: Product page (linked thumbnails)

**Test File**: `tests/e2e/test_link_preservation.py`

**Implementation**:
```python
def test_table_links_preserved():
    """Table cells with links should preserve URLs."""
    url = "https://www.iana.org/domains/reserved"
    result = scrape_url(url)

    # Check IDN table has links
    assert "[XN--KGBECHTV]" in result.markdown
    assert "https://www.iana.org/domains/root/db/xn--kgbechtv.html" in result.markdown

    # Count links (should be 11 in IDN table)
    link_count = result.markdown.count("](https://www.iana.org/domains/root/db/")
    assert link_count >= 11, f"Expected 11+ links, got {link_count}"
```

**Acceptance Criteria**:
- [ ] Tests fail with current bug (validate test correctness)
- [ ] Tests pass after fix implemented
- [ ] CI runs link preservation tests on every commit

**Timeline**: Implement alongside fix (Phase 1.1)

---

## Phase 2: Security Hardening (P1 - Important)

**Goal**: Production-ready security for untrusted URL inputs

### 2.1 SSRF Protection

**Issue**: No validation against private IP ranges or localhost

**Risk**: Local network access, cloud metadata endpoint access (169.254.169.254)

**Implementation**:
```python
# File: web_scraper/models.py

PRIVATE_IP_PATTERNS = [
    r'^https?://127\.',                          # localhost
    r'^https?://10\.',                           # Private Class A
    r'^https?://172\.(1[6-9]|2\d|3[01])\.',     # Private Class B
    r'^https?://192\.168\.',                     # Private Class C
    r'^https?://169\.254\.',                     # Link-local
    r'^https?://localhost',                      # localhost by name
    r'^https?://\[::1\]',                        # IPv6 localhost
    r'^https?://\[fc00:',                        # IPv6 private
]

@field_validator("entrypoints", "include")
def validate_no_private_ips(cls, urls: list[str]) -> list[str]:
    """Reject private IP addresses and localhost to prevent SSRF."""
    import re
    for url in urls:
        if any(re.match(pattern, url, re.IGNORECASE) for pattern in PRIVATE_IP_PATTERNS):
            raise ValidationError(
                f"Private IP or localhost URL not allowed: {url}. "
                "If you need to scrape local services, use the --allow-private flag."
            )
    return urls
```

**Additional**:
- Add `--allow-private` CLI flag for intentional local scraping
- Validate redirect targets (prevent redirects to private IPs)

**Acceptance Criteria**:
- [ ] Private IPs rejected by default
- [ ] `--allow-private` flag allows local scraping
- [ ] Tests cover all private IP ranges
- [ ] Redirect validation prevents bypass

**Timeline**: 2-3 days implementation + testing

---

### 2.2 Credential Redaction in Logs

**Issue**: URLs with tokens/API keys logged as-is

**Risk**: Credentials exposed in logs/manifests

**Implementation**:
```python
# File: web_scraper/exceptions.py

def sanitize_url_for_logging(url: str) -> str:
    """Redact sensitive query parameters from URLs for logging."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)
    if not parsed.query:
        return url

    params = parse_qs(parsed.query)
    sensitive_keys = {
        "token", "api_key", "apikey", "api-key",
        "secret", "password", "pwd", "pass",
        "auth", "authorization", "access_token",
    }

    for key in list(params.keys()):
        if key.lower() in sensitive_keys:
            params[key] = ["[REDACTED]"]

    sanitized_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=sanitized_query))
```

**Usage**:
- Apply in all logging statements
- Apply in manifest URL fields
- Apply in progress output

**Acceptance Criteria**:
- [ ] Logs show `?token=[REDACTED]`
- [ ] Manifest URLs redacted
- [ ] Original URLs used for actual requests (not redacted)
- [ ] Tests verify redaction

**Timeline**: 1-2 days implementation

---

### 2.3 Disk Space Validation

**Issue**: No check for available disk space before crawl

**Risk**: Crawl fails midway when disk fills

**Implementation**:
```python
# File: web_scraper/cli.py

import shutil

def check_disk_space(output_dir: Path, min_gb: float = 1.0) -> None:
    """Warn if available disk space is below threshold."""
    stat = shutil.disk_usage(output_dir)
    available_gb = stat.free / (1024 ** 3)

    if available_gb < min_gb:
        raise ScraperError(
            f"Insufficient disk space: {available_gb:.1f}GB available, "
            f"{min_gb:.1f}GB recommended. Use --force to override."
        )

    if available_gb < 5.0:
        logger.warning(
            f"Low disk space: {available_gb:.1f}GB available. "
            "Large crawls may fail."
        )
```

**Acceptance Criteria**:
- [ ] Crawl aborts if <1GB free
- [ ] Warning if <5GB free
- [ ] `--force` flag to override
- [ ] Tests verify behavior

**Timeline**: 1 day implementation

---

## Phase 3: Format Compatibility (P2 - Enhancement)

**Goal**: Handle edge cases and special content types

### 3.1 JSON Content Preservation

**Current State**: JSON endpoints converted to key-value markdown

**Firecrawl Behavior**: JSON preserved in code fence

**Implementation**:
```python
# File: web_scraper/scrapers/crawl4ai.py

def _detect_json_content(result: CrawlResult) -> bool:
    """Check if response is JSON content."""
    return (
        result.status_code == 200 and
        "application/json" in (result.content_type or "")
    )

def _preserve_json_structure(result: CrawlResult) -> str:
    """Return JSON in markdown code fence."""
    import json
    try:
        # Pretty-print JSON
        data = json.loads(result.html)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return f"```json\n{formatted}\n```"
    except json.JSONDecodeError:
        # Fall back to raw content
        return f"```json\n{result.html}\n```"
```

**Configuration**:
```yaml
# Site config option
preserve_json: true  # Default: false (convert to markdown)
```

**Acceptance Criteria**:
- [ ] JSON endpoints optionally preserved in code fence
- [ ] Matches Firecrawl output format
- [ ] Tests for both modes (preserve vs convert)

**Timeline**: 2-3 days

---

### 3.2 Advanced Table Handling

**Goal**: Handle complex tables (merged cells, nested tables, etc.)

**Test Cases**:
1. Tables with rowspan/colspan
2. Nested tables
3. Tables with mixed content (text + links + images)

**Implementation**: TBD based on Crawl4AI capabilities

**Timeline**: 1 week investigation + implementation

---

## Phase 4: Testing Infrastructure (P1 - Quality Assurance)

**Goal**: Comprehensive test coverage to prevent regressions

### 4.1 Automated Parity Regression Tests

**Purpose**: Ensure quality doesn't degrade over time

**Implementation**:
```python
# File: tests/e2e/test_parity_regression.py

PARITY_URLS = [
    "https://www.iana.org/domains/reserved",  # Table links
    "https://www.iana.org/help/example-domains",  # Simple prose
    "https://httpbin.org/html",  # Long text
]

SIMILARITY_THRESHOLD = 0.95  # 95% similarity required

def test_parity_regression():
    """Ensure output quality remains high vs Firecrawl."""
    for url in PARITY_URLS:
        firecrawl_md = fetch_from_firecrawl_mcp(url)
        webscraper_md = scrape_with_webscraper(url)

        similarity = calculate_similarity(firecrawl_md, webscraper_md)
        assert similarity >= SIMILARITY_THRESHOLD, (
            f"Quality regression on {url}: "
            f"similarity {similarity:.2%} < {SIMILARITY_THRESHOLD:.2%}"
        )
```

**CI Integration**:
- Run on every PR
- Fail build if similarity drops below threshold
- Track similarity trends over time

**Acceptance Criteria**:
- [ ] Tests run in CI
- [ ] Clear failure messages with similarity scores
- [ ] Historical tracking of quality metrics

**Timeline**: 3-4 days implementation + CI setup

---

### 4.2 Comprehensive Link Tests

**Coverage**:
- Table links (P0 - already planned)
- Inline links
- Reference-style links
- Image links
- Anchor links
- Mailto links
- Relative links (conversion to absolute)

**File**: `tests/e2e/test_link_types.py`

**Timeline**: 2-3 days

---

### 4.3 Duplicate Detection Validation

**Purpose**: Ensure duplicate handling is correct (not a bug)

**Test**: Crawl example.com/org/net, verify:
- 3 separate files created
- Content hashes match (expected)
- URLs in frontmatter differ
- No cross-contamination

**File**: `tests/integration/test_duplicate_handling.py`

**Timeline**: 1 day

---

## Phase 5: Documentation Updates (P2 - Usability)

**Goal**: Clear communication of capabilities and limitations

### 5.1 Update README

**Changes**:
- [x] Clarify "Firecrawl-compatible output format" (not API replacement)
- [x] Add Quality Status section with known issues
- [ ] Add link to ROADMAP.md
- [ ] Add link to AUDIT_FIRECRAWL_REPLACEMENT.md
- [ ] Update comparison table with quality metrics

**Timeline**: 1 hour

---

### 5.2 Create Quality Benchmarking Guide

**File**: `docs/parity/parity-methodology.md`

**Content**:
- How to run parity tests
- How to interpret similarity scores
- When to use web-scraper vs Firecrawl
- Known edge cases and workarounds

**Timeline**: 2-3 hours

---

### 5.3 Create Troubleshooting Guide

**File**: `docs/70-reliability/troubleshooting-web-scraper.md`

**Content**:
- Table links missing → use HTML output or wait for fix
- JSON format differs → enable `preserve_json` if needed
- Low disk space → check before crawl
- SSRF errors → use `--allow-private` for local URLs

**Timeline**: 2-3 hours

---

## Success Metrics

### Phase 1 Complete
- [ ] 95%+ similarity to Firecrawl on all test pages
- [ ] 0% link loss in tables
- [ ] Link preservation tests passing

### Phase 2 Complete
- [ ] SSRF protection active
- [ ] Credential redaction in logs
- [ ] Disk space validation

### Phase 3 Complete
- [ ] JSON preservation mode available
- [ ] Advanced table handling tested

### Phase 4 Complete
- [ ] Parity regression tests in CI
- [ ] Comprehensive link tests
- [ ] Duplicate handling validated

### Phase 5 Complete
- [ ] Documentation updated
- [ ] Quality benchmarking guide published
- [ ] Troubleshooting guide available

---

## Release Plan

### v2025.12.1 (Hotfix - 1 week)
- **P0 Fix**: Table link preservation
- **P0 Test**: Link preservation tests
- **Update**: README with known issues fixed

### v2026.01.0 (Security - 2 weeks)
- **P1**: SSRF protection
- **P1**: Credential redaction
- **P1**: Disk space validation
- **P1**: Parity regression tests in CI

### v2026.02.0 (Format Compatibility - 4 weeks)
- **P2**: JSON preservation mode
- **P2**: Advanced table handling
- **P2**: Comprehensive link tests
- **P2**: Documentation updates

---

## Open Questions

1. **Crawl4AI upstream fix**: Should we contribute table link fix to Crawl4AI?
   - **Action**: Test with latest Crawl4AI version, file issue if confirmed

2. **Firecrawl API compatibility**: Should we eventually add API server mode?
   - **Decision**: Out of scope - focus on output format parity, not API parity

3. **Performance vs Quality**: Should we add a "fast mode" with less quality?
   - **Decision**: No - quality-first is core principle

4. **Browser pool limits**: Should we support headless browser farms?
   - **Decision**: Future enhancement, not current roadmap

---

## Contributing

See `.cursor/rules/` for development standards. All changes must:
- Pass existing tests
- Add new tests for new functionality
- Maintain or improve parity scores
- Follow code quality principles (90-code-quality-principles.mdc)
