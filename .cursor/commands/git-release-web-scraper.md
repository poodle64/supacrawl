# Web-scraper Git Release Workflow

## Purpose

Execute a Git release for the **web-scraper** project by applying the **master release reasoning model** and translating it into concrete steps for this single-package repo.

Release reasoning lives in `.cursor/commands/master/intelligent-git-release-workflow.md`.

---

## Scope and Authority

- ✅ Applies web-scraper repo layout and conventions (single package, single version)
- ✅ Translates release reasoning into actionable steps
- ❌ Does not redefine release philosophy or versioning theory
- ❌ Does not override master rules

---

## Release Context

- Single project (no per-component releases)
- Releases are cut from `main`
- Versioning: calendar-based `YYYY.MM.x`
- Tags: `v{YYYY}.{MM}.{x}` (e.g., `v2025.12.0`)
- Version locations: `VERSION`, `pyproject.toml`, `web_scraper/__init__.py`

Assumptions:
- Conventional commits present but not blindly trusted
- CHANGELOG is user-facing
- Tags represent published releases

---

## Execution Steps

### 1) Establish Release Window
- Find most recent tag `v*` (if none, initial release)
- Collect all changes on `main` since that tag

### 2) Analyse Changes
- Review commits and diffs since last tag
- Focus on:
  - Package code (`web_scraper/`)
  - CLI and docs
  - Config and tooling (`pyproject.toml`, `environment.yaml`, `.pre-commit-config.yaml`)

### 3) Categorise by Impact
- Breaking / incompatible
- Feature / enhancement
- Fix / correction
- Internal / maintenance

Use judgment, not just commit prefixes.

### 4) Determine Version Bump
- Calendar versioning: `YYYY.MM.x`
- Patch bump for fixes/maintenance; month bump for features/breaking changes
- **CRITICAL**: Use current date in AEST (Australia/Brisbane). Do NOT use training data dates.

### 5) Update CHANGELOG
- Update root `CHANGELOG.md`
- Add new section for the release version and date (AEST, `YYYY-MM-DD`)
- Aggregate all changes since last version bump into one entry
- Write for end users; lead with breaking changes if any

### 6) Update Version Files
- Update `VERSION` (single line `YYYY.MM.x`)
- Update `[project].version` in `pyproject.toml`
- Update `web_scraper/__init__.py` `__version__`

### 7) Commit Release Intent
- Stage `CHANGELOG.md`, `VERSION`, `pyproject.toml`, `web_scraper/__init__.py`
- Commit using conventional commit:
  - `chore(release): bump version to {version}`

### 8) Create Annotated Tag
- Tag format: `v{version}` (e.g., `v2025.12.0`)
- Command: `git tag -a v{version} -m "Release {version}"`

### 9) Push Release
- `git push origin main`
- `git push origin v{version}`

---

## Time and Dating Standard
- Always use **current date in AEST** (Australia/Brisbane, UTC+10) for calendar versions and CHANGELOG dates
- Never reuse training data dates

---

## Failure Checks (Lightweight)
- CHANGELOG.md updated with new version and date
- VERSION file updated
- pyproject.toml version updated
- `web_scraper/__init__.py` version updated
- Version bump matches impact
- No uncommitted changes remain
- Tag format correct (`vYYYY.MM.x`)

---

## Related Rules and Docs
- Release reasoning: `.cursor/commands/master/intelligent-git-release-workflow.md`
- Process rules: `.cursor/rules/`
- Git workflow: `.cursor/rules/master/10-git-workflow.mdc`
- Versioning guidance: `.cursor/docs/master/10-process/version-files.md`
- Verification: `.cursor/rules/master/73-verification-basics.mdc`
