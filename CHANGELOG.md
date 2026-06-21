# Changelog

All notable changes to supacrawl will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to calendar-based versioning (YYYY.MM.x format).

## [Unreleased]

Turns the off-box telemetry path into a clean, point-at-any-Loki client with first-class setup and backfill tooling and a read-only control-plane API for a separate UI. Builds on the 2026.6.4 remote-shipping foundation. The `RemoteSink` seam, fail-open batching, low-cardinality labels, and environment-only credentials are unchanged; no Loki host is hardcoded anywhere.

### Added

- **Point at any Loki (full auth surface)**: the remote sink mirrors the Grafana Alloy / Promtail client — HTTP basic auth (`metrics_remote_username` + `SUPACRAWL_METRICS_PASSWORD`), an `X-Scope-OrgID` tenant header (`metrics_remote_tenant`), a bearer token (`SUPACRAWL_METRICS_TOKEN`), or no auth — so the same configuration reaches a local/LAN Loki, a gated proxy, a self-hosted multi-tenant Loki, or Grafana Cloud. Basic auth takes precedence over a bearer token when both are set; the password is environment-only and never written to the store. A `WARNING` is logged when only one half of a basic-auth pair is configured.
- **`supacrawl metrics test-remote`**: probes the configured endpoint with one diagnostic event and reports the real HTTP status, latency, and a hint on failure (401/403 → auth, 404 → wrong path, 5xx → server/proxy) — so a misconfigured endpoint surfaces immediately instead of being swallowed by the fail-open sink.
- **`supacrawl metrics replay-remote`**: backfills the local `events.jsonl` to the configured Loki in batches, reporting the ingestion result. Loki de-duplicates identical events so re-running is safe; `--since` limits the window and `--dry-run` previews. (Loki may reject events older than its ingestion window, noted in the command help.)
- **Read-only control-plane HTTP endpoints** (`supacrawl serve`) for a separate UI plane — the engine exposes state, the UI is a separate front-end: `GET /supacrawl/config/schema` (the `x-ui` settings schema), `GET /supacrawl/config` (effective non-secret values plus a secret _presence_ map, never values), and `GET /supacrawl/metrics/summary?days=N`. Writes still go through the config store and credentials stay environment-only.
- **Configurable Loki `job` label**: `metrics_job` / `SUPACRAWL_METRICS_JOB` (default `supacrawl`) sets the stream label applied to shipped events (`{job=...}`), so a deployment can fit its own Loki labelling or distinguish multiple instances.

### Changed

- Remote telemetry is host-neutral and discoverable: neutral example placeholders (`https://loki.example.com/...`), a commented telemetry block in `.env.example`, and a README "Field Telemetry" section plus a "Control plane and the UI seam" guide in `docs/configuration.md` (with an auth matrix incl. Grafana Cloud). No Loki host is hardcoded.

### Fixed

- **Telemetry ships promptly and fails loudly.** A long-running MCP server now flushes buffered events on a ~5-second interval (not only in 25-event batches or at process exit), so a dashboard reading Loki updates in near-real-time. A failing remote push — e.g. a missing or stale `SUPACRAWL_METRICS_TOKEN` — now logs a clear `WARNING` pointing at the fix and `supacrawl metrics test-remote`, instead of being silently dropped by the fail-open path.

### Security

- Credentials embedded in `metrics_remote_url` (`https://user:pass@host/...`) are stripped from the `GET /supacrawl/config` response and from every log line and probe result, so a secret in the URL is never echoed.

## [2026.6.4] - 2026-06-20

Field telemetry can now be shipped off-box to a central log store, completing the path from a local scrape to a Grafana dashboard.

### Added

- **Remote telemetry shipping (configurable log sink)**: supacrawl can now ship each field-telemetry event to an external log store in addition to the local `events.jsonl`, so a central dashboard (Grafana reading Loki) can see quality and usage across runs. Opt-in with `supacrawl config set metrics_remote_url <loki-push-url>` plus an optional `SUPACRAWL_METRICS_TOKEN` bearer token. Loki is the first backend (behind a `RemoteSink` interface, leaving room for OTLP); events are grouped into low-cardinality streams (`{job="supacrawl", kind=...}`) with all detail in the JSON line for LogQL `| json`. Pushes are batched, best-effort, and fail-open with a short timeout — a slow or down endpoint never delays or fails a scrape, and the local log stays authoritative. Privacy carries over from the local sink (domain-only unless `metrics_full_url`). See `docs/configuration.md`.

## [2026.6.3] - 2026-06-20

The GUI-backend-foundation release: supacrawl now persists field telemetry, exposes a typed settings schema and store a control-plane dashboard can build against, and learns per-domain across every scrape path — plus a more trustworthy benchmark.

### Changed

- **Benchmark trustworthiness**: the scrape-quality benchmark no longer lets the independent reference renderer's failures masquerade as scrape regressions. When the renderer under-captures a page (it intermittently grabs only a shell on JS-hydrated pages) the reference-based metrics (token-F1, noise) are discarded for that case and it scores on the trustworthy reference-free signals (coverage, anchors, structure, spacing) — recovering a perfectly-scraped static page from a spurious 57.7 to 91.7. The `web-scraping.dev/antibot/easy` case is reclassified as a capability probe (it returns HTTP 403 to the full stealth ladder, camoufox included, while a benign path on the same host scrapes cleanly — a genuine evasion ceiling, not a regression), so an unbeatable wall no longer drags the headline.

### Added

- **Typed settings, a config store, and a GUI schema** (Closes #138): supacrawl now has one typed settings model resolved from built-in defaults, a local TOML store (`~/.supacrawl/config.toml`), and environment variables — in that order of increasing precedence. Manage it with `supacrawl config get | set | unset | schema | secrets | path`. The model emits a JSON schema annotated with `x-ui` render metadata (group/order/widget/help/visible_when) so a separate control-plane dashboard can render a settings form straight from it; credentials live in a separate environment-only model that never enters the schema or the store (`config secrets` reports presence, never values). The `strategy_memory`, `metrics`, and `metrics_full_url` toggles are read from the resolved config at runtime today; the remaining knobs are exposed for the GUI with command-level adoption rolling out. See `docs/configuration.md`.
- **Per-domain memory and telemetry across every scrape path**: per-domain strategy memory (#130) and the field telemetry sink (#137) now also flow through `crawl`, `batch`, and the `search`/`extract`/`agent` commands — previously only the single `scrape` path learned and recorded. A crawl now learns each domain's cheapest working strategy on the first page and seeds the rest, and every multi-page scrape contributes to the quality/usage log. On by default (opt-out `SUPACRAWL_STRATEGY_MEMORY=0` / `SUPACRAWL_METRICS=0`); the offline benchmark stays deliberately stateless.
- **Field telemetry sink** (Closes #137): supacrawl appends one event per scrape and search — quality verdict, score, attempts, escalation, latency, status, and the registrable domain — to a local, append-only log at `~/.supacrawl/metrics/events.jsonl`, so quality and usage can be tracked over time. On by default for the CLI and MCP server (opt-out `SUPACRAWL_METRICS=0`); domain-only by default for privacy, full URLs/queries opt-in via `SUPACRAWL_METRICS_FULL_URL=1`; the event schema is versioned. Inspect with `supacrawl metrics summary | tail | path | prune`. A `MetricsReader` is the clean read API a separate observability dashboard would consume — the CLI emits, a GUI reads.

## [2026.6.2] - 2026-06-20

The self-improving, MCP-first release (Closes #135). supacrawl now tells the calling agent honestly how good each result is, tries harder automatically when a result is poor, and remembers per domain what worked — so defaults quietly become excellent for the sites you actually use.

### Added

- **Runtime quality signal** (Closes #128): every scrape result carries a structured `quality` field — a verdict (`ok` / `thin` / `js_shell` / `paywall` / `bot_challenge` / `captcha` / `error_status` / `garbled_pdf` / `empty`), a 0–100 score, the reasons behind it, and a concrete `suggestion` when the result is poor — so an agent can decide to accept, retry, or escalate without re-deriving quality from the raw bytes. The signal shares one definition of "good" with the offline benchmark (a shared `supacrawl.quality` module both consume). Surfaced through the MCP tool result, the REST response, and the CLI.
- **Adaptive auto-escalation** (Closes #129): on a recoverable poor verdict (block / CAPTCHA / JS-shell / empty), an unmet `--expect`, or an HTTP/2 TLS rejection, supacrawl automatically walks the stealth/engine ladder — Playwright → Patchright → Camoufox → Camoufox+HTTP/1.1 — with a longer hydration wait, within a bounded budget, keeping the best-scoring attempt. Hard sites just work on defaults; no per-request `engine`/`stealth`/`wait_for` needed. A single `escalate` flag caps it. A detected site-builder (Wix/Squarespace/Framer/Foleon) short-circuits to its tuned engine; a user-pinned engine is respected.
- **Per-domain strategy memory** (Closes #130): supacrawl records, per registrable domain, the cheapest strategy that produced a clean result and seeds the next hit there — the first example-airline.com scrape learns "camoufox + ~5s wait"; the next starts there. A cost-aware champion bandit (EWMA quality, cheaper-equal demotion, clearly-better upgrade, epsilon-greedy downward exploration, instant champion crash on a hard block, TTL decay) lives in a single local JSON document under `~/.supacrawl/strategies/`. On by default for the CLI and MCP server, opt-out with `SUPACRAWL_STRATEGY_MEMORY=0`; inspect and reset with `supacrawl strategy list | show | forget | clear`. With an empty or disabled store, behaviour is identical to the stateless ladder.
- **Search credit/quota visibility** (Closes #136): `supacrawl_health` surfaces per-provider remaining credits (Brave's `X-RateLimit-Remaining`) and the last error; a low-credit warning is emitted below a threshold; the provider chain fails over to the next configured provider on an out-of-credits/blocked error and surfaces the reason. No local usage counter (it is blind to other consumers of the same key).
- **Experiential improvement loop** (Closes #131): the `improve-supacrawl` workflow makes every "improve supacrawl" session compound — read the lessons registry, measure with the benchmark, target the weakest real signal, fix the root cause, confirm a lift with no regression, sharpen the bench when it is blind, and record a dated lesson.

### Changed

- **Search works out of the box or fails loudly** (Closes #132): with no provider key, a keyless search that returns nothing now fails loudly with an actionable error naming `BRAVE_API_KEY` and the free-tier URL — instead of a silent `{success: true, data: []}`. The DuckDuckGo fallback gets the shared browser-realistic header profile. A genuine no-match from a keyed provider stays a clean success.
- **Benchmark hardening** (Closes #134): the independent reference renderer settles hydration before capturing (polling the main-content length until it stabilises), and large PDF cases run in their own concurrency lane with a one-shot isolated retry so they no longer truncate to 0 words under load.
- **Documentation and MCP tool descriptions** (Closes #133): README / CLI / API docs and the MCP tool descriptions now state that search needs a provider key out of the box, describe the quality field and honest `success`, explain that supacrawl auto-escalates (no manual engine/stealth needed), and document per-domain memory and credit visibility.

### Fixed

- **Honest `success`** (Closes #128): an HTTP ≥ 400 response (including an Amazon `/dp/` soft-404 shell), a recognised bot/CAPTCHA interstitial, garbled PDF text, or an empty page is now reported `success=false` with an actionable reason — it was previously reported `success=true`. Hard-fail results are never cached.
- **Clean errors, never a crash** (Closes #129): a mid-fetch error (network, timeout, TLS rejection, a detached iframe on Reddit) returns a clean `success=false` with a hint rather than a raw traceback; the CLI guards `asyncio.run` so a launch error or interrupt exits cleanly.
- **`only_main_content` over-pruning** (Closes #129): when the main-content selector matches a tiny wrapper, supacrawl recovers the fuller page instead of silently dropping the real content.

## [2026.6.1] - 2026-06-15

### Added

- **Scrape-quality benchmark** (`supacrawl bench`, Closes #125): a curated, mostly-frozen corpus of real-world pages — static, articles, docs, SPA, infinite-scroll, data tables, PDF, CJK/RTL i18n, anti-bot, Australian government tax-law (HTML + PDF), and AU retail — scored 0–100 on completeness, token-F1, gold-anchor presence, boilerplate absence, structure, and inter-word spacing against an independent browser reference. Subcommands `bench run | compare | list | show` persist a per-run JSON document, a flat `metrics.jsonl`, and a run index for trend tracking. Volatile or reference-unfriendly targets are marked as capability probes and excluded from the regression index.
- **`word_spacing` benchmark metric**: detects PDF-extraction defects that fuse adjacent words into one token, guarding the PDF cases against regression. It counts only over-long all-ASCII alphabetic runs, so non-Latin scripts (CJK, Arabic) are never falsely penalised, and short bodies are skipped.
- **Real-world benchmark cases**: a frozen ATO government PDF (RAG/tax-law), two ATO gov-CMS HTML pages, a live AU pet-food retailer (JSON-LD Article), and a JS-rendered GitHub README (microdata).

### Fixed

- **PDF inter-word spacing for RAG quality**: LaTeX/academic PDFs extracted with words run together ("Thedominantsequencetransduction…") because pdfplumber's default gap threshold (3pt) is wider than those PDFs' inter-word spaces. Tightening `x_tolerance` to 2 restores spacing without over-splitting digitally-generated PDFs such as government publications; the arXiv reference PDF goes from ~5,300 fused tokens to ~9,400 correctly-spaced words.
- **JS-shell pages now escalate to a real render** (Closes #126): single-page-app shells whose only payload was inline JSON (e.g. `quotes.toscrape.com/js/`) looked content-rich to the static fast path and never rendered. The JS-requirement estimate now ignores inline JSON/template scripts, so these pages escalate to the browser.
- **PDF detection by content-type and magic bytes** (Closes #127): extensionless PDF URLs (e.g. `arxiv.org/pdf/…` and government content-API URLs) are detected via the `Content-Type` header and the `%PDF-` signature, not only the `.pdf` extension, and the already-fetched bytes are reused for extraction instead of being downloaded twice.

## [2026.6.0] - 2026-06-14

### Added

- **HTTP-first fast path** (Closes #119): `scrape` now tries a cheap HTTP GET before launching a browser, escalating to Playwright only when a render-needed or bot-challenge signal fires (the same heuristics `diagnose` uses). Static pages return several times faster and without browser cost. Enabled by default; disable with `--no-http-first` (CLI), `httpFirst: false` (REST), or `http_first=False` (MCP). Browser-only requests (screenshot, PDF, actions, device emulation, stealth, or a non-default engine) skip the fast path automatically.
- **Optional robots.txt enforcement for crawl** (Closes #119): `crawl` can honour each origin's `robots.txt`, skipping disallowed URLs and respecting `Crawl-delay`. It is opt-in — a crawl fetches the URLs it is given by default — so enable it with `--respect-robots` (CLI), `respect_robots=True` (MCP), or `ignoreRobotsTxt: false` (REST).
- **Per-host courtesy throttle for crawl** (Closes #119): a minimum inter-request gap per host, set with `--delay` (CLI), `delay` (REST), or `request_delay` (MCP). A `robots.txt` `Crawl-delay` automatically raises the gap. Prevents a personal IP being rate-limited or banned during a crawl.
- **`--expect` content gate** (Closes #121): assert that specific content is present before a scrape returns. A bare integer is a minimum word count; any other value is matched first as a CSS selector then as a text substring. When the assertion is unmet, the HTTP-first path escalates to the browser, the browser waits for a selector-shaped expectation to hydrate, and an still-unmet assertion (after a stealth + longer-wait retry) returns `success=False` with a remediation hint instead of a pre-hydration skeleton. Available as `--expect` (CLI), `expect` (REST/MCP).
- **Agent-readable, remediation-shaped errors** (Closes #123): scrape failures and MCP tool errors now carry a concrete, honest recovery hint instead of an opaque stack trace — `[HINT: ...]` for timeouts (raise the timeout/wait_for), DNS/connection/TLS faults, and 4xx/5xx responses, and a "try only_main_content=False" hint on thin-content warnings. Anti-bot failures keep the availability-aware stealth hint; failures with no useful action get no speculative advice (the #107 lesson). Lets an agent retry with a corrected parameter without human intervention.
- **Embedded structured-data extraction (no LLM)** (Closes #120): a new `structuredData` format deterministically harvests the data a site already publishes — schema.org JSON-LD (with `@graph` flattening), Next.js `__NEXT_DATA__`, HTML microdata, and OpenGraph — returned as JSON with no model call. More reliable and far cheaper than the LLM `json` path for facts like prices, ratings, authors, and dates. Available as `-f structuredData` (CLI), `structuredData` in `formats` (REST, surfaced under `structuredData`), and the MCP scrape tool.
- **Search recency, topic, and domain filters** (Closes #122): `search` now accepts `time_range` (day/week/month/year), `start_date`/`end_date`, `topic` (general/news/finance), and `include_domains`/`exclude_domains`, mapped onto each provider's native API (Brave `freshness`, Tavily native fields, Serper/SerpAPI `tbs`, Exa published-date + `category`) or synthesised as `site:` query operators where a provider has no native support. An agent can scope a search at the provider instead of post-filtering. Available across CLI (`--time-range`, `--start-date`, `--end-date`, `--topic`, `--include-domain`, `--exclude-domain`), REST, and the MCP search tool.
- **Agent self-onboarding: `SKILL.md`, `llms.txt`, and `install-skill`** (Closes #124): a concise, shippable `SKILL.md` teaches an agent how to choose between scrape/search/map/crawl/llm-extract/agent and which flags to set, including failure recovery; a root `llms.txt` gives the standard agent-landing overview. `supacrawl install-skill` registers the skill in one command (`./.claude/skills/` by default, `--user` for home, `--dir` for Cursor/Codex/other runtimes).

### Internal

- **Extracted `services/detection.py`**: the pure page-classification heuristics (CDN/WAF, JS framework, bot protection, login wall, render-needed estimate, recommendation generation) moved out of the `diagnose` MCP tool into a shared module so the scrape fast path, crawl, and diagnose share one implementation. A dead `BOT_DETECTION_PATTERNS` constant in `diagnose.py` was removed.
- **Extracted `ScrapeService._assemble_result()`**: the output-format assembly and caching tail is now shared by the browser path and the HTTP-first path, eliminating duplication.
- **Dropped two vestigial result models and tidied the E2E suite**: removed `ContentStats` and `ProcessMetadata`, which were defined but never populated or surfaced; replaced swallowed-exception mock scaffolding with deterministic browser fakes; made the search and the site-dependent crawl/map tests skip gracefully when a live provider or page yields nothing; bounded external-link discovery; and gave the timeout tests short explicit timeouts so they fail fast.

### Documentation

- Brought the CLI and REST references current with the HTTP-first fast path, the `--expect` content gate, the `structuredData` format, the content-extraction dial, search recency/topic/domain filters, and the crawl robots/delay options.

## [2026.5.0] - 2026-05-15

### Added

- **`/healthz` and `/readyz` HTTP probes on the embedded MCP server** (Closes poodle64/mcp-servers#270): The MCP server now exposes the canonical container-orchestration probes alongside the legacy `/health` route. `/healthz` always returns 200 while the process is alive (suitable for liveness); `/readyz` returns 200 once the FastMCP app is serving (suitable for readiness). Containers using the standard `/healthz` Docker healthcheck no longer need a per-service exception. Routes are registered automatically by `BaseMCPServer.__init__`; no caller changes required.
- **`SUPACRAWL_MASK_ERROR_DETAILS` env var** (default `True`): Operators can flip this to `False` in dev/CI to expose raw exception text in MCP tool errors. Production should keep the default. Wired to FastMCP 3.x's `mask_error_details` constructor flag, replacing the silent fallback to FastMCP's own `FASTMCP_MASK_ERROR_DETAILS` env var.
- **`ToolAnnotations` on all 8 MCP tools**: Every scraping/search tool now declares `readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True`; health and diagnose tools declare the same minus `openWorldHint=False`. Lets MCP clients render correct affordances and skip pre-call confirmations on read-only operations.

### Internal

- **Re-vendored `mcp_common` from `poodle64/mcp-servers`**: Replaced the months-stale single-file vendored copy with the current package layout (`server/`, `validators/`, plus new `redaction.py`, `executors/`, `host_shell/`). This is what unlocks `/healthz` and brings the MCP server into line with the rest of the household's MCP fleet. Internal imports rewritten from absolute (`from mcp_common.X`) to relative (`from .X`) to support the nested sub-package layout (`supacrawl.mcp.mcp_common`); `mcp_common.__version__` is now read lazily inside `register_server_info_resource()` to avoid a circular import.
- **`SupacrawlSettings.mask_error_details` field** added to `config.py` under the existing `SUPACRAWL_` env_prefix.
- One pre-existing test (`test_settings_loads_defaults` asserting `search_provider == "duckduckgo"`) remains failing; the assertion drifted out of step with the `brave` default in 2026.3.0. Tracked separately, not introduced by this release.

## [2026.3.2] - 2026-03-21

### Added

- **REST API server via `supacrawl serve`** (Closes #109): Firecrawl v2-compatible REST API with Supacrawl-native extensions. Existing Firecrawl clients (n8n, LangChain, LlamaIndex) work as drop-in backends by pointing their base URL at Supacrawl. Install with `pip install supacrawl[api]`.
  - Synchronous endpoints: POST /scrape, POST /map, POST /search
  - Async job endpoints: POST /crawl, POST /extract, POST /batch/scrape with GET polling and DELETE cancellation
  - Native endpoints: GET /supacrawl/health, POST /supacrawl/diagnose, POST /supacrawl/summary
  - Credential verification stub: GET /team/credit-usage (for n8n compatibility)
  - Optional Bearer token authentication via `SUPACRAWL_API_KEY`
  - In-memory async job store with configurable TTL and concurrency limits
  - camelCase request/response translation matching the v2 protocol
- **Foleon platform detection** with auto-tuned scrape settings

## [2026.3.1] - 2026-03-08

### Fixed

- **Playwright/Patchright lower bound regressed to >=1.58.0** (Closes #104): v2026.3.0 accidentally bumped the Playwright lower bound from `>=1.40.0` to `>=1.58.0`, breaking NixOS users whose package repositories provide 1.52.0 (stable) or 1.57.0 (unstable). Audit confirmed supacrawl uses only core Playwright APIs available since 1.0; restored `>=1.40.0` bound. Added inline comments and CLAUDE.md guardrail to prevent recurrence.

## [2026.3.0] - 2026-03-04

### Features

- **Multi-provider search with automatic fallback** (Closes #101): Refactored monolithic search into a pluggable provider architecture. Supports 6 providers (Brave, Tavily, Serper, SerpAPI, Exa, DuckDuckGo) with automatic fallback on quota exhaustion, rate limiting, or CAPTCHA detection. Configure via `SUPACRAWL_SEARCH_PROVIDERS` env var or `--provider` CLI flag
- **Configurable search rate limiting** (Closes #99): New `SUPACRAWL_SEARCH_RATE_LIMIT` env var. Enhanced health endpoint shows per-provider status and rate limit configuration
- **Brave Search as default provider** (Closes #95): Brave Search replaces DuckDuckGo as the default. DuckDuckGo is deprecated but remains as a last-resort fallback
- **Realistic browser headers for search** (Closes #96): Search requests use full browser-like headers (User-Agent, Sec-CH-UA, Accept-Language) to avoid bot detection. Locale-aware via `SUPACRAWL_LOCALE`
- **Camoufox anti-detection engine** (Closes #80): New `--engine camoufox` option provides Tier 3 anti-bot protection using patched Firefox. Effective against Akamai Bot Manager and advanced TLS fingerprinting. Install: `pip install supacrawl[camoufox]`
- **Change tracking** (Closes #81): New `-f changeTracking` format detects content changes between scrapes by comparing against cached previous versions. Supports `--change-tracking-modes git-diff` for unified diffs
- **PDF URL parsing** (Closes #82): Auto-detects `.pdf` URLs and extracts text directly, bypassing the browser. OCR fallback available via `pip install supacrawl[pdf-ocr]`. Controlled with `--parse-pdf [auto|fast|ocr|off]`
- **Mobile device emulation** (Closes #83): New `--mobile` and `--device TEXT` flags for scraping as mobile devices using Playwright device descriptors. Use `--list-devices` to see available presets
- **Iframe content extraction** (Closes #85): New `--expand-iframes [none|same-origin|all]` option (default: same-origin) expands iframe content inline during scraping
- **JSON comparison mode for change tracking** (Closes #87): `--change-tracking-modes json` compares structured extracted fields between scrapes
- **Change tracking in crawl** (Closes #88): `-f changeTracking` now works in the `crawl` command with `--change-tracking-modes` and `--cache-dir` support
- **Per-request engine in MCP tools** (Closes #90): `engine` parameter on `supacrawl_scrape` and `supacrawl_crawl` MCP tools allows per-request engine selection. Server default configurable via `SUPACRAWL_ENGINE` environment variable

### Fixed

- **DuckDuckGo CAPTCHA detection** (Closes #97): Detect and report CAPTCHA challenges from DuckDuckGo instead of returning empty results
- **ERR_HTTP2_PROTOCOL_ERROR automatic fallback** (Closes #92): Two-stage auto-retry chain (Chromium to Camoufox to Camoufox + HTTP/1.1) handles servers that reject Chromium's TLS fingerprint
- **Camoufox async wrapper** (Closes #91): Use correct `AsyncCamoufox` context manager instead of `AsyncNewBrowser`
- **CLI ScrapeService resource leak**: ScrapeService is now properly closed in the CLI search command's finally block

### Performance

- **Reduced scrape overhead by ~1.7s per page** (Closes #89): Removed unnecessary PDF HEAD request from the scrape hot path

## [2026.2.3] - 2026-02-26

### Fixed

- **Playwright version constraint** (Closes #79): Relaxed from `>=1.49.0` to `>=1.40.0,<2.0.0`. Supacrawl only uses stable core Playwright APIs, so the previous lower bound was unnecessarily restrictive. This allows distributions like NixOS and Guix to pair supacrawl with their system-provided Playwright browser binaries

### Documentation

- Added "System-Managed Playwright Browsers" section to README for users with distro-provided Playwright binaries

### Internal

- CI: use reusable auto-label workflow from master project

## [2026.2.2] - 2026-02-22

### Features

- **CSS background-image extraction**: Extract image URLs from CSS `background-image` and `background` shorthand properties, improving image discovery on sites that use CSS for hero images and backgrounds
- **Improved logo detection**: Better logo identification for site builders (Wix `<wow-image>`, Squarespace `data-section-type`, Framer `data-framer-name`) and nested `<img>` elements inside `role="img"` containers
- **Correlation IDs in MCP responses**: All MCP tool responses now include `correlation_id` for request tracing and debugging
- **WordPress and CSS counter preprocessors**: New site-specific preprocessors for WordPress content and CSS counter-based ordered lists, producing cleaner markdown output
- **MCP map `ignore_cache` parameter**: New parameter to bypass cached URL discovery results
- **MCP map title fallback and timezone detection**: Map results include `<title>` tag fallback for pages without `<meta>` titles, and automatic timezone detection from page content

### Fixed

- **MCP headless browser windows** (Closes #78): Browser windows no longer flash visibly during MCP operations. The `headless` parameter now propagates to all internal `BrowserManager` instances, including CAPTCHA solving and stealth retry paths
- **Screenshot cache key collision**: `screenshot_full_page` setting is now included in the cache key, preventing incorrect cache hits when the same URL is scraped with different screenshot settings
- **CrawlService browser lifecycle**: CrawlService now accepts an injected `BrowserManager`, avoiding duplicate browser instances when used from the MCP server

### Internal

- Remove Docker MCP files (`Dockerfile.mcp`, `docker-compose.mcp.yaml`); MCP server now runs natively via `supacrawl-mcp`
- Add MCP server section to README with installation and configuration instructions

## [2026.2.1] - 2026-02-21

### Features

- **Embedded MCP server**: the MCP server is now bundled as an optional extra (`pip install supacrawl[mcp]`), replacing the standalone server in `mcp-servers`. Includes all tools (scrape, crawl, map, search, extract, summary, diagnose, health), prompts, resources, structured logging, correlation IDs, exception mapping, and input validation. Install and run with `supacrawl-mcp --transport stdio`.
- Docker support for running the MCP server (`Dockerfile.mcp`, `docker-compose.mcp.yaml`)

### Fixed

- Remove duplicate `supacrawl_health` tool registration in MCP server
- MCP exception mapping gap: internal errors now correctly map to JSON-RPC error codes (Closes #69)

## [2026.2.0] - 2026-02-16

### Fixed

- Strip `javascript:` pseudo-protocol links completely during HTML to markdown conversion. These UI controls (print, share, email buttons) are now removed entirely following industry best practice from Readability.js, Newspaper3k, and Trafilatura. Fixes #67.

### Internal

- Add auto-label workflow for GitHub issues with AI-powered classification
- Ignore issue archive directories in git

## [2026.1.0] - 2026-01-12

Initial public release.

### Features

- **scrape** - Extract content from a single URL as markdown, HTML, or JSON
- **crawl** - Crawl websites with URL discovery, resume support, and parallel processing
- **map** - Discover URLs from sitemaps and page links with streaming progress
- **search** - Web search via DuckDuckGo or Brave with optional scraping
- **llm-extract** - LLM-powered structured data extraction
- **agent** - Autonomous web agent for multi-step data gathering
- **cache** - Local caching with statistics and pruning

### Capabilities

- Playwright-based browser automation with anti-bot evasion
- Optional enhanced stealth mode via Patchright (`pip install supacrawl[stealth]`)
- Optional CAPTCHA solving via 2Captcha (`pip install supacrawl[captcha]`)
- Page actions: click, scroll, wait, type, screenshot, JavaScript execution
- Multiple output formats: markdown, HTML, rawHtml, links, images, screenshot, PDF, JSON
- LLM integration: Ollama (local), OpenAI, Anthropic
- Site-specific preprocessors for improved markdown output (MkDocs Material, etc.)
- Proxy support with authentication
- Locale settings: country, language, timezone
- Python 3.12+ support
