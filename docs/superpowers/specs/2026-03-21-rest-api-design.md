# REST API Design

**Issue:** #109
**Date:** 2026-03-21
**Status:** Draft

## Summary

Add a REST API to Supacrawl via a new `supacrawl serve` CLI command. The API is compatible with the Firecrawl v2 REST protocol, allowing existing clients (n8n Firecrawl node, LangChain, LlamaIndex, curl) to use Supacrawl as a drop-in self-hosted backend. Supacrawl-native endpoints extend the surface with capabilities the v2 protocol doesn't cover.

## Architecture

### CLI command

```shell
supacrawl serve [--host 0.0.0.0] [--port 8308] [--reload]
```

Launches a FastAPI app served by uvicorn. Separate process from the MCP server.

### Package structure

```text
src/supacrawl/api/
├── __init__.py
├── app.py              # FastAPI app factory + lifespan
├── auth.py             # Bearer token dependency
├── dependencies.py     # Service instance management
├── jobs.py             # In-memory async job store
├── models/
│   ├── __init__.py
│   ├── scrape.py       # Request/response models for scrape + batch
│   ├── crawl.py        # Request/response models for crawl
│   ├── map.py          # Request/response models for map
│   ├── search.py       # Request/response models for search
│   └── extract.py      # Request/response models for extract
└── routers/
    ├── __init__.py
    ├── scrape.py        # POST /scrape
    ├── crawl.py         # POST /crawl, GET /crawl/{id}, DELETE /crawl/{id}
    ├── map.py           # POST /map
    ├── search.py        # POST /search
    ├── extract.py       # POST /extract, GET /extract/{id}
    ├── batch.py         # POST /batch/scrape, GET /batch/scrape/{id}
    ├── team.py          # GET /team/credit-usage (credential verification stub)
    └── supacrawl.py     # /supacrawl/* native endpoints
```

### Dependency: `supacrawl[api]`

New optional extra in `pyproject.toml`:

```toml
[project.optional-dependencies]
api = ["fastapi>=0.115.0", "uvicorn[standard]>=0.34.0"]
```

### Lifespan

The FastAPI app factory creates shared service instances on startup and tears them down on shutdown. Reuses the `SupacrawlServices` wrapper from the MCP server (`mcp/api_client.py`).

`ExtractService` is not part of `SupacrawlServices`. It is created per-request in the extract router, injected with the shared `ScrapeService`. This matches the existing MCP pattern where extract tools create the service ad-hoc.

The extract endpoint wraps the awaitable `ExtractService.extract()` call in a background asyncio task, updating the job store on completion. The caller receives a job ID immediately.

## Endpoints

### Compatible REST surface

| Endpoint | Method | Service | Behaviour |
|---|---|---|---|
| `/scrape` | POST | `ScrapeService.scrape()` | Synchronous |
| `/crawl` | POST | `CrawlService.crawl()` | Async; returns job ID |
| `/crawl/{id}` | GET | Job store | Poll status + paginated results |
| `/crawl/{id}` | DELETE | Job store | Cancel |
| `/map` | POST | `MapService.map()` | Synchronous (collects all MapEvents) |
| `/search` | POST | `SearchService.search()` | Synchronous |
| `/extract` | POST | `ExtractService.extract()` | Async; returns job ID |
| `/extract/{id}` | GET | Job store | Poll status + result |
| `/batch/scrape` | POST | `ScrapeService.scrape()` x N | Async; returns job ID |
| `/batch/scrape/{id}` | GET | Job store | Poll status + paginated results |
| `/team/credit-usage` | GET | Stub | Returns valid response for credential verification |

### Supacrawl-native endpoints

| Endpoint | Method | Service | Notes |
|---|---|---|---|
| `/supacrawl/health` | GET | All | Version, uptime, service status. Always unauthenticated. |
| `/supacrawl/diagnose` | POST | BrowserManager | Pre-scrape diagnostics (CDN, bot protection, JS) |
| `/supacrawl/summary` | POST | ScrapeService + LLM | Page summarisation |

## Request/Response Translation

### General principles

The REST API accepts camelCase (matching the v2 protocol). The API layer translates to snake_case for service calls. Fields not supported by Supacrawl are accepted silently and ignored, so clients do not need modification.

The `proxy` field has different semantics: v2 uses `"basic"/"enhanced"/"auto"`, Supacrawl uses URL or bool. Translation: `"basic"` and `"auto"` map to `True` (use default proxy); `"enhanced"` maps to `True`; a URL string is passed through directly.

The `storeInCache` field maps to Supacrawl's cache behaviour: `false` sets `max_age=0` to bypass cache.

### Scrape request fields (`POST /scrape`)

| v2 field | Service parameter | Notes |
|---|---|---|
| `url` | `url` | Required |
| `formats` | `formats` | Supacrawl extras: `"images"`, `"branding"`, `"pdf"` |
| `onlyMainContent` | `only_main_content` | Default `true` |
| `waitFor` | `wait_for` | Milliseconds |
| `timeout` | `timeout` | Milliseconds |
| `includeTags` | `include_tags` | CSS selectors |
| `excludeTags` | `exclude_tags` | CSS selectors |
| `mobile` | `mobile` | Viewport emulation |
| `actions` | `actions` | Same schema; pass-through |
| `location` | `locale_config` | `{ country, languages }` |
| `headers` | `headers` | Custom request headers |
| `maxAge` | `max_age` | v2 sends ms; divide by 1000 for service (expects seconds) |
| `proxy` | `proxy` | See translation above |
| `skipTlsVerification` | N/A | Ignored |
| `removeBase64Images` | N/A | Ignored |
| `blockAds` | N/A | Ignored |
| `storeInCache` | `max_age` (indirect) | `false` sets `max_age=0` to bypass cache |
| `integration` | N/A | Ignored |
| `zeroDataRetention` | N/A | Ignored |
| `minAge` | N/A | Ignored |

Supacrawl-only parameters (`engine`, `device`, `expand_iframes`, `parse_pdf`, `screenshot_full_page`) are not exposed via the v2-compatible surface. They can be added to `/supacrawl/scrape` later if needed.

### Crawl request fields (`POST /crawl`)

| v2 field | Service parameter | Notes |
|---|---|---|
| `url` | `url` | Required |
| `limit` | `limit` | Default 10000 (v2) vs 100 (Supacrawl); use v2 default |
| `maxDiscoveryDepth` | `max_depth` | |
| `includePaths` | `include_patterns` | Regex patterns on URL path |
| `excludePaths` | `exclude_patterns` | Regex patterns on URL path |
| `sitemap` | `sitemap` | `"skip"/"include"/"only"` |
| `allowExternalLinks` | `allow_external_links` | |
| `allowSubdomains` | `allow_subdomains` | |
| `maxConcurrency` | `concurrency` | |
| `delay` | N/A | Ignored (Supacrawl manages its own pacing) |
| `ignoreQueryParameters` | `ignore_query_params` | |
| `scrapeOptions` | Nested scrape params | Same mapping as scrape fields above |
| `webhook` | N/A | Ignored (not supported in v1) |
| `prompt` | N/A | Ignored |
| `regexOnFullURL` | N/A | Ignored |
| `crawlEntireDomain` | N/A | Ignored |

### Map request fields (`POST /map`)

| v2 field | Service parameter | Notes |
|---|---|---|
| `url` | `url` | Required |
| `limit` | `limit` | Default 5000 |
| `search` | `search` | Filter/order by relevance |
| `sitemap` | `sitemap` | `"skip"/"include"/"only"` |
| `includeSubdomains` | `include_subdomains` | |
| `ignoreQueryParameters` | `ignore_query_params` | |
| `ignoreCache` | `ignore_cache` | |
| `timeout` | `timeout` | |
| `location` | `locale_config` | |

### Search request fields (`POST /search`)

| v2 field | Service parameter | Notes |
|---|---|---|
| `query` | `query` | Required |
| `limit` | `limit` | Default 5 |
| `sources` | `sources` | v2 sends `[{type: "web"}]`; translate to `["web"]`. Unknown types dropped. |
| `timeout` | `timeout` | |
| `scrapeOptions` | `scrape_options` | Nested scrape params |
| `tbs` | N/A | Ignored |
| `location` | N/A | Ignored (Supacrawl uses provider-level config) |
| `country` | N/A | Ignored |
| `categories` | N/A | Ignored |
| `ignoreInvalidURLs` | N/A | Ignored |
| `enterprise` | N/A | Ignored |

### Extract request fields (`POST /extract`)

| v2 field | Service parameter | Notes |
|---|---|---|
| `urls` | `urls` | Required |
| `prompt` | `prompt` | |
| `schema` | `schema` | JSON Schema object |
| `scrapeOptions` | Nested scrape params | |
| `enableWebSearch` | N/A | Ignored |
| `ignoreSitemap` | N/A | Ignored |
| `includeSubdomains` | N/A | Ignored |
| `showSources` | N/A | Ignored |
| `ignoreInvalidURLs` | N/A | Ignored |

### Response shape (scrape example)

```json
{
  "success": true,
  "data": {
    "markdown": "...",
    "html": "...",
    "rawHtml": "...",
    "links": ["..."],
    "screenshot": "...",
    "metadata": {
      "title": "...",
      "description": "...",
      "sourceURL": "...",
      "url": "...",
      "statusCode": 200,
      "language": "..."
    },
    "actions": { "screenshots": [], "scrapes": [] },
    "branding": { "..." },
    "changeTracking": { "..." }
  }
}
```

Translation is handled via Pydantic models with `alias` fields. CamelCase serialisation names map to snake_case internal names.

### Search response translation

The v2 protocol buckets results by source type. Supacrawl's `SearchResult.data` is a flat list with a `source_type` field. The API layer groups items by `source_type` into the bucketed shape.

Field mapping per bucket:

| v2 field | `SearchResultItem` field | Notes |
|---|---|---|
| `web[].title` | `title` | |
| `web[].url` | `url` | |
| `web[].description` | `description` | |
| `web[].markdown` | `markdown` | Only present if `scrapeOptions` requested |
| `images[].imageUrl` | `thumbnail` | Renamed |
| `images[].title` | `title` | |
| `images[].url` | `url` | |
| `news[].title` | `title` | |
| `news[].snippet` | `description` | Renamed |
| `news[].url` | `url` | |

```json
{
  "success": true,
  "data": {
    "web": [{ "title": "...", "url": "...", "description": "...", "markdown": "..." }],
    "images": [{ "title": "...", "imageUrl": "...", "url": "..." }],
    "news": [{ "title": "...", "url": "...", "snippet": "..." }]
  }
}
```

### Map response shape

```json
{
  "success": true,
  "links": [{ "url": "...", "title": "...", "description": "..." }]
}
```

## Async Job Store

For crawl, extract, and batch scrape operations.

### Design

- In-memory dict keyed by UUID job ID
- Each job: `status` (scraping/completed/failed), `total`, `completed`, `data` (list), `created_at`, `expires_at`
- Background asyncio task runs the actual operation, updates job store as results arrive
- Jobs expire after configurable TTL (default 24h, via `SUPACRAWL_API_JOB_TTL`)
- Pagination: GET endpoints return up to 10MB per response with a `next` URL

### Concurrency limits

Maximum 3 concurrent async jobs (crawl + extract + batch combined). Additional submissions return 429. This prevents a single user from exhausting browser resources. Configurable via `SUPACRAWL_API_MAX_JOBS` (default 3).

### No persistence

Jobs are lost on restart. Acceptable for homelab use. The job store interface is clean enough to back with SQLite later if needed.

## Authentication

### Mechanism

- Bearer token: `Authorization: Bearer <token>`
- Configured via `SUPACRAWL_API_KEY` environment variable
- If `SUPACRAWL_API_KEY` is set: token must match, 401 on mismatch
- If `SUPACRAWL_API_KEY` is not set: auth disabled, all requests pass
- `/supacrawl/health` is always unauthenticated

### Implementation

FastAPI dependency function (`get_api_key`), not middleware. Routers opt in; health endpoint opts out.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SUPACRAWL_API_KEY` | None | Bearer token. Unset = auth disabled |
| `SUPACRAWL_API_HOST` | `0.0.0.0` | Bind address |
| `SUPACRAWL_API_PORT` | `8308` | Bind port |
| `SUPACRAWL_API_JOB_TTL` | `86400` | Job expiry in seconds |
| `SUPACRAWL_API_MAX_JOBS` | `3` | Max concurrent async jobs |

## Error Handling

All errors return:

```json
{
  "success": false,
  "error": "Human-readable message"
}
```

Status codes: 400 (bad request), 401 (auth), 404 (job not found), 500 (internal). FastAPI's 422 validation errors are remapped to 400 with the same `{ success, error }` shape.

## CORS

Permissive (all origins) by default. Appropriate for local/homelab deployment.

## Security Profile

This is a Profile 0 service (local/homelab, single-user, trusted network). No rate limiting beyond the concurrent job cap. Auth is optional. If deployed on an untrusted network, users should put it behind a reverse proxy with TLS and rate limiting.

## Testing

### Approach

High-value e2e flows, not mock-heavy unit tests. The test suite proves that a real HTTP request hits the real service layer and returns a correctly shaped response.

### Test structure

```text
tests/test_api/
├── conftest.py           # FastAPI TestClient fixture, shared helpers
├── test_scrape.py        # POST /scrape e2e flow
├── test_crawl.py         # POST /crawl → GET /crawl/{id} lifecycle
├── test_map.py           # POST /map e2e flow
├── test_search.py        # POST /search e2e flow
├── test_extract.py       # POST /extract → GET /extract/{id} lifecycle
├── test_batch.py         # POST /batch/scrape lifecycle
├── test_auth.py          # Auth with key, auth without key
├── test_jobs.py          # Job creation → poll → expiry lifecycle
├── test_native.py        # /supacrawl/* endpoints
└── test_translation.py   # camelCase ↔ snake_case boundary cases
```

### What's tested

- **E2E flows**: Real TestClient → real service layer → verify response shape and key fields
- **Translation boundary**: camelCase/snake_case mapping, unknown fields silently ignored, defaults applied
- **Job lifecycle**: Create → poll → complete (or fail) → expire
- **Auth**: Key set + valid token, key set + invalid token, key unset

### What's not tested here

- Scraping correctness (covered by existing service tests)
- Browser lifecycle (covered by existing browser tests)
- Individual service logic (covered by existing test suite)

## Dependencies

### New (optional extra `api`)

- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.34.0`

## Project files to update

- `.claude/rules/00-project-foundations.md`: Update "Does NOT provide REST API" to reflect the new API
- `.claude/CLAUDE.md`: Add REST API to the stack description
- `README.md`: Document the `serve` command and API usage
- `CHANGELOG.md`: Add entry for REST API feature

### Already available

- `pydantic` (core dep)
- `starlette` (transitive via fastmcp, but FastAPI brings its own)
- `httpx` (core dep, also used for TestClient)
