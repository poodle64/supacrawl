# Supacrawl

Zero-infrastructure CLI web scraper with LLM extraction, for developers working from the terminal — `pip install` and go, no Docker, databases, or services.

## Scope

- **Does**: CLI commands (`scrape`, `crawl`, `map`, `search`, `llm-extract`, `agent`, `cache`) plus an optional REST API (`supacrawl serve`, `supacrawl[api]`) and an MCP server (`supacrawl-mcp`).
- **Does not**: no web UI; no database — output goes to stdout/files and a local cache; no auth beyond browser-level; not a hosted service (local execution only).

## Design constraints

- LLM extraction stays provider-pluggable (Ollama / OpenAI / Anthropic) — never lock to one provider.
- Every command must support both stdout and file output; machine-readable output is JSON.
- The local cache must stay user-controllable (`cache` command: stats/clear/prune).
- Stealth scraping runs on Patchright; the engine auto-escalates on a poor result (`playwright → patchright → camoufox`). The ladder and per-domain strategy memory are documented in `docs/configuration.md`.

## Running it

- Setup needs **all extras**: `uv sync --all-extras` (direnv runs it on `cd`) then `playwright install chromium`. A bare `uv sync` silently omits the `stealth`/`captcha`/`camoufox`/`pdf-ocr` extras and scraping breaks at runtime.
- Quality gate before done: `ruff check src/ && mypy src/` and `pytest -q -m "not e2e"` (drop the marker to include live-network E2E). See README and `docs/development/testing.md`.
- Config and env-var reference (the `SUPACRAWL_*` catalogue and provider keys): `docs/configuration.md`. LLM selection is `SUPACRAWL_LLM_PROVIDER` / `SUPACRAWL_LLM_MODEL` / `OLLAMA_HOST` (see `src/supacrawl/llm/config.py`).

## Pitfalls

- **Playwright/Patchright lower bound `>=1.40.0` is intentional** (NixOS compatibility; #79, #104). Do NOT bump it unless new Playwright APIs are actually used.

## CI deviations from the household standard

- **No `auto-label-issues` caller.** `rules-library/core/ci-workflow-standard.md` requires every repo to delegate issue auto-labelling to the master-project reusable, and permits a public repo that cannot resolve it to omit the caller provided the omission is recorded. supacrawl is public and `poodle64/master-project` is private, so the reusable is unresolvable here; labels are applied at creation time by the `/git-issue` skill instead. Recorded 2026-08-11 — the omission was correct but had never been written down, which the umbrella rule treats as a defect in its own right.
- **`publish.yaml` inlines the `publish-wheels` reusable instead of calling it.** Same public→private constraint: sibling libraries (redactyl, ragify, core-memory — all private) call `poodle64/master-project/.github/workflows/publish-wheels.yaml@main`, but a public repo cannot resolve a private reusable. So `publish.yaml` replicates that reusable's logic (build-time version stamp, wheel-only build, devpi upload from the runner-host credential file — never a GitHub secret, 409-as-skip idempotency) plus a post-upload verify that the index serves our wheel from `poodle64/prod/+f/` rather than the squatted PyPI mirror. Keep it aligned with the reusable when that changes. Recorded 2026-08-15.
