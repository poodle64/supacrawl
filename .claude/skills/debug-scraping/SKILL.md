---
name: debug-scraping
description: Diagnose and fix web scraping failures in Supacrawl. Use when scraping fails, returns empty content, times out, gets blocked by anti-bot protection, or produces unexpected results.
allowed-tools: Bash, Read, Grep, Glob, WebFetch
---

# Debug Scraping Issues

Systematic diagnosis of web scraping failures in Supacrawl.

## When This Skill Activates

- Scraping returns empty or incomplete content
- Timeout errors during page load
- Anti-bot detection or CAPTCHA challenges
- JavaScript content not rendering
- Unexpected HTTP errors (403, 429, 503)
- Content structure doesn't match expectations

## Diagnostic Process

### Step 1: Reproduce the Issue

First, reproduce with debug logging enabled:

```bash
SUPACRAWL_LOG_LEVEL=DEBUG supacrawl scrape "URL" --format markdown
```

Capture:
- The exact error message
- The URL being scraped
- Any correlation ID in the error

### Step 2: Categorise the Failure

| Symptom | Likely Cause | Jump To |
|---------|--------------|---------|
| Empty markdown output | JS not rendered, content in iframe | Step 3a |
| Timeout error | Slow page, wait strategy wrong | Step 3b |
| 403/Access Denied | Anti-bot detection | Step 3c |
| 429 Too Many Requests | Rate limiting | Step 3d |
| Connection refused | Network/proxy issue | Step 3e |
| Wrong content extracted | Selector/conversion issue | Step 3f |

### Step 3a: JavaScript Rendering Issues

**Symptoms**: Empty content, "Loading..." text, missing dynamic elements

**Diagnosis**:
```bash
# Try with longer wait
supacrawl scrape "URL" --wait-for 5000

# Try networkidle wait strategy
supacrawl scrape "URL" --wait-until networkidle
```

**Check**:
- Does the site require JavaScript? View source vs rendered DOM
- Is content loaded via XHR/fetch after page load?
- Is content in an iframe?

**Fixes**:
- Increase `--wait-for` time for slow JS
- Use `--wait-until networkidle` for XHR-heavy sites
- Check if content is in iframe (Playwright won't cross iframe boundaries by default)

### Step 3b: Timeout Issues

**Symptoms**: "Timeout waiting for page", operation cancelled

**Diagnosis**:
```bash
# Check with extended timeout
supacrawl scrape "URL" --timeout 60000
```

**Check**:
- Is the site actually slow or unresponsive?
- Is there a redirect chain?
- Is the network stable?

**Fixes**:
- Increase timeout: `--timeout 60000` (60 seconds)
- Use `--wait-until load` instead of `networkidle` for sites that never stop loading
- Check for infinite redirect loops

### Step 3c: Anti-Bot Detection

**Symptoms**: 403 Forbidden, CAPTCHA page, "Access Denied", Cloudflare challenge

**Diagnosis**:
```bash
# Try with stealth mode
supacrawl scrape "URL" --stealth

# Check what the bot sees
supacrawl scrape "URL" --format rawHtml | head -100
```

**Check**:
- Does the raw HTML show a CAPTCHA or challenge page?
- Is Cloudflare/Akamai/PerimeterX protection active?
- Are browser fingerprints being detected?

**Fixes**:
- Enable stealth mode: `--stealth` (uses Patchright)
- Slow down requests if scraping multiple pages
- Some sites require human verification - these cannot be scraped automatically

### Step 3d: Rate Limiting

**Symptoms**: 429 errors, temporary blocks, "Too Many Requests"

**Diagnosis**:
- Check if error occurs on first request or after multiple
- Check response headers for rate limit info

**Fixes**:
- Add delays between requests when crawling
- Respect `Retry-After` headers
- Reduce concurrency

### Step 3e: Network Issues

**Symptoms**: Connection refused, DNS resolution failed, SSL errors

**Diagnosis**:
```bash
# Test basic connectivity
curl -I "URL"

# Check DNS
dig domain.com
```

**Check**:
- Is the site actually accessible?
- Is there a proxy configuration issue?
- Are there SSL certificate problems?

**Fixes**:
- Verify URL is correct and site is up
- Check proxy settings if using one
- For SSL issues, check certificate validity

### Step 3f: Content Extraction Issues

**Symptoms**: Content extracted but wrong/incomplete, formatting broken

**Diagnosis**:
```bash
# Get raw HTML to inspect
supacrawl scrape "URL" --format rawHtml > page.html

# Compare with markdown
supacrawl scrape "URL" --format markdown > page.md
```

**Check**:
- Is the content present in raw HTML?
- Is the markdown converter handling it correctly?
- Are there encoding issues?

**Fixes**:
- Check if `only_main_content` is excluding desired content
- Look for unusual HTML structures that confuse the converter
- Check for encoding issues in source

## Code Investigation

If the issue is in Supacrawl itself, investigate:

| Component | Location | Purpose |
|-----------|----------|---------|
| Browser management | `src/supacrawl/services/browser.py` | Playwright lifecycle, page fetching |
| Content extraction | `src/supacrawl/services/scrape.py` | Main scrape logic |
| Markdown conversion | `src/supacrawl/services/converter.py` | HTML to Markdown |
| Stealth mode | Uses Patchright instead of Playwright | Anti-detection |

## Common Patterns

### Site Uses Heavy JavaScript
```bash
supacrawl scrape "URL" --wait-for 5000 --wait-until networkidle
```

### Site Has Anti-Bot Protection
```bash
supacrawl scrape "URL" --stealth
```

### Site Is Slow
```bash
supacrawl scrape "URL" --timeout 60000 --wait-until load
```

### Need to Debug What Browser Sees
```bash
supacrawl scrape "URL" --format screenshot --output debug.png
```

## Escalation

If none of the above resolves the issue:

1. **Check GitHub Issues**: Similar problem may be reported
2. **Capture debug output**: `SUPACRAWL_LOG_LEVEL=DEBUG` with full output
3. **Test in real browser**: Does the URL work in Chrome/Firefox?
4. **Create minimal reproduction**: Single URL that demonstrates the issue
