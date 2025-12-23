# Phase 8: Marie Kondo Cleanup

## Context

You are implementing Phase 8 of the Firecrawl-parity rebuild. This phase removes all cruft, obsolete files, debug scripts, and working documents that no longer serve a purpose. Keep only what's needed for the production codebase.

**Branch:** `refactor/firecrawl-parity-v2`
**Depends On:** Phase 7 (E2E testing complete)

## Principle

Ask of each file: "Does this serve the production codebase?" If no, delete it.

---

## CRITICAL: Task 0 - Fix Crawl4AI References in Documentation

**Phase 6 FAILED to clean up documentation.** These files STILL reference Crawl4AI and MUST be updated FIRST:

### README.md (HIGHEST PRIORITY - this is what users see first!)

The README still says we use Crawl4AI. This is WRONG. Update ALL of these:
- "wraps Crawl4AI" → "uses Playwright"
- "using Crawl4AI + Playwright" → "using Playwright"
- Remove "Uses Crawl4AI SDK"
- Remove Crawl4AI bug references (we don't use it anymore)
- Remove `crawl4ai-setup` and `crawl4ai-doctor` commands
- Remove Crawl4AI documentation link

### .claude/CLAUDE.md
- "Crawl4AI, Playwright" → "Playwright"

### docs/40-usage/*.md (ALL files)
- `markdown-fixes.md`: "Crawl4AI" → "upstream markdown conversion"
- `creating-site-configs-web-scraper.md`: Remove ALL Crawl4AI references
- `USAGE_GUIDE.md`: Remove "Crawl4AIScraper" and "Crawl4AI knowledge"
- `cli-usage-web-scraper.md`: Remove Crawl4AI provider references

### docs/README.md
- Remove reference to crawl4ai-quality-best-practices.md (file was deleted)

### docs/70-reliability/*.md
- `retry-logic-web-scraper.md`: Remove Crawl4AI provider sections
- `testing-web-scraper.md`: Remove ALL Crawl4AI test examples

### Planning docs to DELETE entirely
These are obsolete planning docs:
```bash
rm docs/plan-map-firecrawl-parity.md
rm docs/architecture-firecrawl-parity.md
```

### Verification for Task 0
```bash
grep -ri "crawl4ai" --include="*.md" . | grep -v ".claude/prompts" | grep -v "CHANGELOG"
# MUST return NOTHING (CHANGELOG can keep historical reference)
```

**DO NOT PROCEED TO OTHER TASKS UNTIL THIS VERIFICATION PASSES.**

---

## Task 1: Delete Root Level Cruft

Delete these files from the project root:

```bash
# Completed audit/working docs
rm AUDIT_FIRECRAWL_REPLACEMENT.md
rm BUG_REPORT_CRAWL4AI_SPA.md
rm DOCUMENTATION_UPDATES.md
rm ROADMAP.md

# Debug/test scripts (obsolete - Crawl4AI removed)
rm debug_sharesight.py
rm test_spa_delay.py
```

**Keep:** `README.md`, `CHANGELOG.md`, `pyproject.toml`, `.env.example`

---

## Task 2: Delete Audit Artifacts

```bash
rm -rf audit_artifacts/
```

This directory contains completed audit work that's no longer needed.

---

## Task 3: Delete Debug Site Configs

```bash
rm sites/audit-test.yaml
rm sites/debug-test1-no-filter.yaml
rm sites/debug-test2-no-fixes.yaml
rm sites/debug-test3-both-disabled.yaml
rm sites/sharesight-api-manual.yaml
```

**Keep:** `sites/meta.yaml`, `sites/sharesight-api.yaml`, `sites/example_site.yaml`, `sites/template.yaml`

---

## Task 4: Fix Broken Tests

These tests reference deleted Crawl4AI code:

### `tests/unit/test_no_custom_html_to_markdown_fallback.py`

This test checks `crawl4ai_result.py` which no longer exists. Either:
- Delete the test file entirely, OR
- Update to test the new converter.py instead

### `tests/unit/test_guardrails.py`

Remove references to:
- `crawl4ai` in the forbidden imports list
- `e2e/test_crawl4ai_quality.py` in allowed files

### `tests/integration/test_providers.py`

This tests the old Crawl4AI provider. Either:
- Delete if no longer relevant, OR
- Update to test the new Playwright-based services

---

## Task 5: Clean Up Obsolete Docs

Check and remove docs that reference deleted features:

```bash
# Check for obsolete docs
ls docs/40-usage/
```

Remove any docs that only apply to Crawl4AI. Keep docs that are still relevant.

---

## Task 6: Clean Up Phase Prompts

The phase prompts in `.claude/prompts/` served their purpose. Consider:
- Keep `orchestration-firecrawl-parity.md` as historical record
- Delete individual phase prompts OR move to `.claude/prompts/archive/`

---

## Task 7: Verify Clean State

After cleanup, verify:

```bash
# No debug scripts in root
ls *.py 2>/dev/null
# Should return nothing

# No audit artifacts
ls audit_artifacts/ 2>/dev/null
# Should fail (directory deleted)

# No debug site configs
ls sites/debug*.yaml sites/audit*.yaml 2>/dev/null
# Should fail

# Tests pass
pytest tests/unit/ -v --tb=short
# Should pass with no import errors

# No references to deleted files
grep -r "crawl4ai_result\|crawl4ai_quality\|debug_sharesight" --include="*.py" .
# Should return nothing
```

---

## Task 8: Update .gitignore

Add patterns to prevent future cruft:

```gitignore
# Debug scripts
debug_*.py
test_*.py
!tests/

# Working docs
AUDIT_*.md
BUG_REPORT_*.md
DOCUMENTATION_*.md
```

---

## Verification Checklist

- [ ] Root directory has only essential files (README, CHANGELOG, pyproject.toml, etc.)
- [ ] No `audit_artifacts/` directory
- [ ] No debug site configs
- [ ] All tests pass (no import errors for deleted files)
- [ ] No orphaned references to deleted code

---

## Commit Message

```
chore: marie kondo cleanup - remove obsolete files and cruft

- Delete completed audit/working docs (AUDIT_*, BUG_REPORT_*, ROADMAP)
- Remove debug scripts (debug_sharesight.py, test_spa_delay.py)
- Delete audit_artifacts/ directory
- Remove debug site configs
- Fix tests referencing deleted Crawl4AI code
- Update .gitignore to prevent future cruft

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```
