# Web-Scraper Workflow Analysis and Usability Improvements

**Document Purpose:** Consolidated analysis of web-scraper's current workflow, mental model, friction points, and proposed usability improvements within foundational architectural constraints.

**Date:** 2025-12-18

---

## 1. Current Workflow (As Implemented)

### 1.1 Pre-Crawl: YAML Site Configuration

Users must manually create a YAML file in the `sites/` directory before any crawl can execute.

**Example:** `sites/sharesight-api.yaml`

```yaml
id: sharesight-api
name: Sharesight API Documentation
entrypoints:
  - https://portfolio.sharesight.com/api
include:
  - https://portfolio.sharesight.com/api/**
exclude: []
max_pages: 500
formats:
  - markdown
  - html
  - json
only_main_content: true
include_subdomains: false
```

**Key constraints:**
- Filename (without `.yaml`) becomes the site identifier used in CLI commands
- The `id` field must match the filename (validated on load via Pydantic)
- All fields are validated against `SiteConfig` model schema
- Validation failures raise `ValidationError` with correlation ID

### 1.2 Crawl Execution Flow

**Command:** `web-scraper crawl <site-name>`

**Step-by-step execution:**

1. **Load site config** from `sites/{site}.yaml`
   - Pydantic validates YAML against `SiteConfig` model
   - Validation failures raise `ValidationError` with helpful context

2. **Determine snapshot path**
   - If `--resume latest`: Find most recent resumable snapshot in `corpora/{site_id}/`
   - If `--resume <snapshot_id>`: Use specific snapshot
   - Otherwise: Generate new snapshot ID using Australia/Brisbane timestamp (`YYYY-MM-DD_HHMM`)

3. **Check for resume state**
   - If resuming: Load `crawl_state.json` from snapshot directory
   - Extract `completed_urls`, `pending_urls`, `failed_urls`, `checkpoint_page`
   - If snapshot status is `completed`, warn and start fresh crawl

4. **Initialise scraper**
   - Create `Crawl4AIScraper` instance
   - Build Crawl4AI `AsyncWebCrawler` with browser config (Playwright, stealth mode)
   - Build `RateLimiter` from politeness config
   - Build `CrawlerRunConfig` with markdown generator, LLM config (if enabled)

5. **Create snapshot writer**
   - Instantiate `IncrementalSnapshotWriter` for the snapshot path
   - Writer creates snapshot directory structure: `corpora/{site_id}/{snapshot_id}/`
   - Creates format subdirectories: `markdown/`, `html/`, `json/`

6. **Execute crawl**
   - If `--from-map`: Load URLs from map file, crawl only those URLs
   - Otherwise: Use Crawl4AI's `BFSDeepCrawlStrategy` with entrypoints
   - For each page crawled:
     - Extract content in requested formats (markdown, html, json)
     - Apply markdown fixes if enabled in config
     - Write page files to format directories (preserving URL hierarchy)
     - Update manifest incrementally
     - Update crawl state (add to `completed_urls`, remove from `pending_urls`)
     - Write state to `crawl_state.json`

7. **Handle interruption**
   - On Ctrl+C: Set crawl state to `aborted`, write final manifest and state
   - Raise `CrawlInterrupted` with pages completed and snapshot path
   - User can resume with `--resume latest`

8. **Complete crawl**
   - Set crawl state to `completed`
   - Write final manifest with all page metadata, stats, correlation ID
   - Write checksums file (`checksums.sha256`)
   - Write structured logs (`run.log.jsonl`)
   - Print snapshot path to user

### 1.3 Snapshot Creation and Naming

**Snapshot ID generation:**

Snapshot IDs are timestamp-based using Australia/Brisbane timezone:

```python
now = datetime.now(ZoneInfo("Australia/Brisbane"))
snapshot_id = now.strftime("%Y-%m-%d_%H%M")
```

**Example:** `2025-12-15_0847` (15 December 2025, 08:47 AEST)

**Snapshot directory structure:**

```
corpora/
└── sharesight-api/
    └── 2025-12-15_0847/
        ├── manifest.json
        ├── crawl_state.json
        ├── checksums.sha256
        ├── run.log.jsonl
        ├── markdown/
        │   ├── api.md
        │   └── api/
        │       ├── 2/
        │       │   └── overview.md
        │       └── 3/
        │           └── overview.md
        ├── html/
        │   └── (same structure)
        └── json/
            └── (same structure)
```

**Key properties:**
- **Immutable**: Each crawl creates a new snapshot (never overwrites)
- **Self-contained**: All metadata, content, and state in one directory
- **Resumable**: `crawl_state.json` tracks progress for interrupted crawls
- **Verifiable**: `checksums.sha256` provides integrity checking

### 1.4 Resume Semantics

**Current behaviour:**

- User must explicitly pass `--resume latest` or `--resume <snapshot_id>` to resume
- `--resume latest` finds the most recent snapshot where `status != completed`
- If the most recent snapshot is `completed`, resume is not possible (starts fresh)
- Resume loads `crawl_state.json` and skips already-completed URLs

**Resume workflow:**

```bash
# Start crawl
$ web-scraper crawl sharesight-api
# ... crawling ...
^C  # Interrupt with Ctrl+C

# Resume crawl
$ web-scraper crawl sharesight-api --resume latest
Resuming from 2025-12-15_0847: 8 pages completed, 5 pending
```

### 1.5 Chunking Workflow

Chunking is a separate command that operates on completed snapshots.

**Command:** `web-scraper chunk <site-id> <snapshot-id>`

**Workflow:**

1. User runs crawl: `web-scraper crawl sharesight-api`
2. Crawl completes, prints snapshot path
3. User copies snapshot ID from output
4. User runs chunk: `web-scraper chunk sharesight-api 2025-12-15_0847`
5. Chunker reads markdown files from snapshot
6. Chunker creates `chunks.jsonl` in snapshot directory

**Two-step workflow is required:** Crawl does not automatically chunk. User must run separate command with snapshot ID.

### 1.6 Artefacts Produced

**1. `manifest.json` (snapshot root)**

**Purpose:** Snapshot metadata and page index for downstream consumers.

**Contains:**
- Site metadata: `site_id`, `site_name`, `provider`, `snapshot_id`, `created_at`
- Crawl metadata: `entrypoints`, `total_pages`, `formats`, `status`
- Page array: Each page has `url`, `title`, `content_hash`, `formats` (paths to files)
- Stats: Word counts, token estimates, language distribution, status codes
- Boilerplate hashes: Repeated content patterns (for deduplication)

**Why:** Provides machine-readable index for loading snapshots without filesystem traversal.

**2. `crawl_state.json` (snapshot root)**

**Purpose:** Resumable crawl state for interrupted crawls.

**Contains:**
- `status`: `pending`, `in_progress`, `completed`, `aborted`
- `completed_urls`: URLs successfully crawled
- `pending_urls`: URLs discovered but not yet crawled
- `failed_urls`: URLs that failed after retries
- `checkpoint_page`: Number of pages completed
- `last_updated`: Timestamp of last state write

**Why:** Enables Ctrl+C safety and resumption without re-crawling completed pages.

**3. Format directories (`markdown/`, `html/`, `json/`)**

**Purpose:** Extracted content in requested formats.

**Structure:** Preserves URL hierarchy as directory structure:
- Root URLs (`https://example.com/`) → `index.{ext}`
- Path segments (`/api/2/overview`) → `api/2/overview.{ext}`

**Why:** Natural navigation, collision-free, preserves site structure.

**4. `checksums.sha256` (snapshot root)**

**Purpose:** SHA-256 checksums for all files in snapshot.

**Why:** Integrity verification, archival validation, deduplication.

**5. `run.log.jsonl` (snapshot root)**

**Purpose:** Structured crawl logs (one JSON object per line).

**Why:** Debugging, auditing, performance analysis.

**6. `chunks.jsonl` (optional, created by `chunk` command)**

**Purpose:** LLM-ready chunks with metadata.

**Contains:** One JSON object per line with:
- `url`: Source page URL
- `title`: Source page title
- `chunk_index`: Zero-based chunk index
- `content`: Chunk text content
- `heading_hierarchy`: Markdown heading context
- `chunk_type`: Content type (code, list, table, paragraph)
- Optional: `summary` (if `--ollama-summarize` used)

**Why:** Pre-chunked content for RAG systems, LLM fine-tuning, or embedding generation.

### 1.7 How Users Return to Work with Results

**Scenario 1: Inspect snapshot manually**

```bash
# List snapshots for a site
ls corpora/sharesight-api/

# Read manifest
cat corpora/sharesight-api/2025-12-15_0847/manifest.json | jq .

# Read markdown content
cat corpora/sharesight-api/2025-12-15_0847/markdown/api.md
```

**Scenario 2: Chunk snapshot for LLM consumption**

```bash
# Chunk snapshot (creates chunks.jsonl)
web-scraper chunk sharesight-api 2025-12-15_0847

# Read chunks
cat corpora/sharesight-api/2025-12-15_0847/chunks.jsonl | jq .
```

**Scenario 3: Resume interrupted crawl**

```bash
# Resume most recent crawl
web-scraper crawl sharesight-api --resume latest

# Resume specific snapshot
web-scraper crawl sharesight-api --resume 2025-12-15_0847
```

**Scenario 4: Compress for archival**

```bash
# Create .tar.gz archive
web-scraper compress sharesight-api 2025-12-15_0847

# Extract later
web-scraper extract corpora/sharesight-api/2025-12-15_0847.tar.gz
```

**Scenario 5: Programmatic consumption**

```python
import json
from pathlib import Path

# Load manifest
manifest_path = Path("corpora/sharesight-api/2025-12-15_0847/manifest.json")
manifest = json.loads(manifest_path.read_text())

# Load chunks
chunks_path = Path("corpora/sharesight-api/2025-12-15_0847/chunks.jsonl")
chunks = [json.loads(line) for line in chunks_path.read_text().splitlines()]
```

---

## 2. Mental Model the System Assumes

### 2.1 Core Concepts

The workflow assumes users think in terms of **sites as persistent entities with versioned snapshots**.

**Core concepts:**

1. **Site**: A configuration that defines what to scrape (YAML file)
2. **Snapshot**: A point-in-time capture of a site's content (timestamped directory)
3. **Corpus**: A collection of snapshots for a site (directory tree)
4. **Formats**: Multiple representations of the same content (markdown, html, json)
5. **Chunks**: Optional post-processing for LLM consumption (JSONL file)

**User journey:**

1. Define a site once (YAML config)
2. Crawl periodically to create snapshots
3. Each snapshot is immutable and self-contained
4. Optionally chunk snapshots for downstream use
5. Compare snapshots over time (manual or programmatic)

### 2.2 Intended User Profile

The system is designed for:

- **Developers or power users** comfortable with CLI and filesystem navigation
- **Local-first workflows** (no SaaS, no API keys, runs entirely on local machine)
- **Periodic scraping** (hours/days, not seconds) for corpus building
- **Reproducible, versioned corpora** for LLM training, RAG, or archival
- **Configuration-driven** workflows (YAML configs, not ad-hoc scraping)

The system is **not** designed for:

- Non-technical users expecting GUI
- High-frequency or real-time scraping
- One-off, ad-hoc scraping without configuration
- API-first workflows (like Firecrawl)
- Users who prefer hosted services

### 2.3 What Must Be Learned vs What Is Obvious

**Learned through repetition:**

1. **YAML-first**: Users must create a YAML file before doing anything. This is not discoverable from the CLI alone.
2. **Two-step identifier**: Filename must match `id` field. This is a validation rule, not a natural constraint.
3. **Snapshot IDs are timestamps**: Users don't choose snapshot IDs, they're auto-generated. This is only clear after running a crawl.
4. **Separate chunk step**: Chunking is a separate command, not part of the crawl. Users must know to run `chunk` after `crawl`.
5. **Resume semantics**: `--resume latest` finds the most recent resumable snapshot, but "resumable" means `status != completed`. This is not obvious.

**What helps:**

- README provides clear workflow examples
- `list-sites` and `show-site` commands aid discovery
- CLI help text is comprehensive
- Error messages include correlation IDs and helpful context

**What doesn't help:**

- No `init` or `create-site` command to scaffold YAML files
- No `list-snapshots` command to see what's been crawled
- No `show-snapshot` command to inspect snapshot metadata
- No `diff` command to compare snapshots

---

## 3. Clunkiness and Friction

### 3.1 First-Time User Friction

**Friction point 1: YAML config creation**

- **Experience**: User must manually create a YAML file with exact schema
- **Pain**: No scaffolding, no interactive prompts, no validation until crawl time
- **Workaround**: Copy `sites/template.yaml` and edit (requires reading docs)

**Friction point 2: Snapshot ID discovery**

- **Experience**: User runs crawl, gets a snapshot path printed, must remember or copy it
- **Pain**: No `list-snapshots` command to see what's been created
- **Workaround**: `ls corpora/{site_id}/` in shell

**Friction point 3: Two-step workflow (crawl → chunk)**

- **Experience**: User runs `crawl`, gets markdown/html, but no chunks
- **Pain**: Must run separate `chunk` command with snapshot ID
- **Workaround**: None, this is by design

**Friction point 4: Resume semantics**

- **Experience**: User runs `crawl --resume latest`, but it starts fresh if last crawl completed
- **Pain**: "Latest" means "latest resumable", not "latest snapshot"
- **Workaround**: User must understand `status` field in `crawl_state.json`

### 3.2 Firecrawl-Comparison Friction

**Friction point 5: No API, only CLI**

- **Experience**: Firecrawl users expect `POST /scrape` with JSON body, get CLI instead
- **Pain**: Must learn CLI flags, YAML configs, filesystem navigation
- **Workaround**: None, this is architectural

**Friction point 6: No instant results**

- **Experience**: Firecrawl returns JSON response immediately, web-scraper writes to filesystem
- **Pain**: Must navigate filesystem to find results
- **Workaround**: Use `--verbose` to see progress, read manifest after crawl

**Friction point 7: No map-first workflow**

- **Experience**: Firecrawl has `POST /map` to discover URLs before scraping
- **Pain**: web-scraper has `map` command, but it's separate from `crawl`
- **Workaround**: Use `map` to generate URL list, then `crawl --from-map`

### 3.3 "Just Scrape This Site" User Friction

**Friction point 8: YAML config is mandatory**

- **Experience**: User wants to run `web-scraper crawl https://example.com`
- **Pain**: Must create YAML file first, can't pass URL directly
- **Workaround**: None, YAML is required

**Friction point 9: Snapshot IDs are opaque**

- **Experience**: User sees `corpora/example/2025-12-15_0847/` and wonders what `0847` means
- **Pain**: Timestamp format is not explained in output
- **Workaround**: Read docs or infer from multiple snapshots

**Friction point 10: No single-command workflow**

- **Experience**: User wants one command to scrape and chunk
- **Pain**: Must run `crawl`, then `chunk` separately
- **Workaround**: Shell script or alias

---

## 4. Intentional vs Accidental Complexity

### 4.1 Classification Table

| Element | Why It Exists | Benefit | Cost | Classification |
|---------|---------------|---------|------|----------------|
| **YAML configs as primary interface** | Configuration-driven design, reusable site definitions | Reproducible crawls, version-controllable configs | High barrier to entry, no ad-hoc scraping | **Intentional trade-off** |
| **Filename must match `id` field** | Validation rule to prevent mismatches | Prevents user error (loading wrong config) | Extra cognitive load, not enforced by filesystem | **Incidental complexity** |
| **Snapshot IDs are timestamps** | Automatic versioning, no user input required | Collision-free, chronological ordering | Opaque to users, not human-readable | **Intentional trade-off** |
| **Separate `chunk` command** | Chunking is optional, not all users need it | Keeps crawl fast, allows multiple chunk strategies | Two-step workflow, must remember snapshot ID | **Intentional trade-off** |
| **Resume requires `--resume latest`** | Explicit opt-in to resumption | Prevents accidental resumption | Users must know to use flag, "latest" semantics unclear | **Incidental complexity** |
| **No `list-snapshots` command** | Not implemented yet | None | Users must use `ls` in shell | **Probably unnecessary** |
| **No `show-snapshot` command** | Not implemented yet | None | Users must read `manifest.json` manually | **Probably unnecessary** |
| **No `init` or `create-site` command** | Not implemented yet | None | Users must copy template manually | **Probably unnecessary** |
| **No single-command scrape+chunk** | Separation of concerns, optional chunking | Flexibility, keeps crawl focused | Extra step for common workflow | **Intentional trade-off** |
| **Formats are config-driven, not inferred** | Explicit control over output | Predictable output, no surprises | Must specify in YAML, can't override easily | **Intentional trade-off** |
| **Corpus output is filesystem-based** | Local-first design, no database | Simple, portable, inspectable | No query layer, must navigate filesystem | **Intentional trade-off** |
| **`map` is separate from `crawl`** | Discovery vs execution separation | Can inspect URLs before crawling | Two-step workflow, must save map file | **Intentional trade-off** |

### 4.2 Foundational Elements (Do Not Change)

**1. Snapshot-based corpus layout**

- **Why foundational**: Downstream consumers depend on this structure
- **Contract**: `corpora/{site_id}/{snapshot_id}/manifest.json` with page array
- **Risk**: Breaking this breaks all existing integrations

**2. YAML site configurations**

- **Why foundational**: Configuration-driven design is core to the project
- **Contract**: `sites/{name}.yaml` with `SiteConfig` schema
- **Risk**: Removing YAML would require complete redesign

**3. Immutable snapshots**

- **Why foundational**: Each crawl creates new snapshot, never overwrites
- **Contract**: Snapshot IDs are unique, content is never modified after creation
- **Risk**: Allowing in-place updates breaks versioning guarantees

**4. Crawl4AI as scraping engine**

- **Why foundational**: web-scraper wraps Crawl4AI, doesn't implement scraping
- **Contract**: `Scraper.crawl(config: SiteConfig) -> list[Page]`
- **Risk**: Replacing Crawl4AI would require rewriting scraper layer

### 4.3 Flexible Elements (Open to Rethinking)

**1. CLI command structure**

- **Current**: Separate commands for `map`, `crawl`, `chunk`, `compress`, `extract`
- **Flexibility**: Could add combined commands (e.g., `scrape-and-chunk`)
- **Constraint**: Must maintain backwards compatibility with existing commands

**2. Snapshot ID format**

- **Current**: Timestamp-based (`YYYY-MM-DD_HHMM`)
- **Flexibility**: Could add user-provided IDs or semantic versioning
- **Constraint**: Must remain unique and sortable

**3. Resume semantics**

- **Current**: `--resume latest` finds most recent resumable snapshot
- **Flexibility**: Could add `--resume-or-new` to always resume if possible
- **Constraint**: Must not break existing resume behaviour

**4. Chunking workflow**

- **Current**: Separate `chunk` command after `crawl`
- **Flexibility**: Could add `--chunk` flag to `crawl` for single-command workflow
- **Constraint**: Must keep chunking optional (not all users need it)

**5. Site config creation**

- **Current**: Manual YAML file creation
- **Flexibility**: Could add `init` command to scaffold configs
- **Constraint**: Must not make YAML optional (config-driven design is core)

**6. Snapshot discovery**

- **Current**: No CLI commands to list or inspect snapshots
- **Flexibility**: Could add `list-snapshots`, `show-snapshot`, `diff-snapshots`
- **Constraint**: Must not duplicate filesystem operations (keep CLI focused)

---

## 5. Proposed Usability Improvements Within Foundational Constraints

### 5.1 Foundational Constraints (Non-Negotiable)

- YAML site configs remain required
- Snapshot-based, immutable corpora remain
- Filesystem-first design remains
- Crawl4AI remains the scraping engine
- CLI-only interface remains

### 5.2 Improvement Summary Table

| Improvement | User Pain | Why Safe | Category | Risk |
|-------------|-----------|----------|----------|------|
| **1. Add `list-snapshots <site>` command** | Users must use `ls corpora/{site}/` to see what snapshots exist. No way to see snapshot metadata (status, page count, date) without reading manifests. | Adds discovery, doesn't change snapshot structure or creation. Pure read operation on existing filesystem layout. | CLI affordance | **Low** - Read-only, no state changes |
| **2. Auto-derive `id` from filename, make field optional** | Users must ensure YAML filename matches `id` field, creating duplicate information and validation errors. Cognitive overhead for no architectural benefit. | Filename is already the source of truth for CLI commands. Making `id` optional (defaulting to filename stem) removes redundancy without changing how sites are identified or loaded. | Validation improvement | **Low** - Backwards compatible (explicit `id` still works) |
| **3. Add `--chunk` flag to `crawl` command** | Users must remember snapshot ID, run separate `chunk` command. Two-step workflow for common use case. No way to "scrape and chunk in one go". | Chunking already happens post-crawl. Flag triggers chunking after successful crawl completion using the just-created snapshot. Doesn't change crawl behaviour or snapshot layout. | CLI affordance | **Low** - Optional flag, doesn't change default behaviour |
| **4. Make `--resume latest` the default when snapshot exists** | Users must explicitly pass `--resume latest` even when there's obviously an incomplete snapshot. Resume semantics are hidden behind a flag. | Crawl already checks for existing snapshots. Making resume the default when `status != completed` removes a flag without changing resume logic. Add `--no-resume` to force fresh crawl. | Default behaviour tweak | **Medium** - Changes default, but adds escape hatch |
| **5. Add `init <site-name>` command to scaffold YAML** | Users must manually copy `sites/template.yaml` and edit. No interactive way to create a valid config. High barrier to first crawl. | Creates a YAML file from template with prompts for required fields. Doesn't change YAML requirement or schema. Pure convenience wrapper around file creation. | CLI affordance | **Low** - Generates files users would create manually anyway |

### 5.3 Detailed Improvement Specifications

#### Improvement 1: `list-snapshots <site>` command

**User experience:**

```bash
$ web-scraper list-snapshots sharesight-api
2025-12-15_0847  completed   13 pages   2025-12-15 08:49:43
2025-12-14_1623  aborted      8 pages   2025-12-14 16:25:11
2025-12-13_0912  completed   13 pages   2025-12-13 09:15:02
```

**Why it's safe:** Reads existing manifests, displays metadata. No writes, no state changes. Filesystem structure unchanged.

**Implementation:** Read `corpora/{site_id}/*/manifest.json`, extract `snapshot_id`, `status`, `total_pages`, `created_at`. Sort by timestamp descending.

---

#### Improvement 2: Auto-derive `id` from filename

**Current pain:**

```yaml
# sites/sharesight-api.yaml
id: sharesight-api  # Must match filename
name: Sharesight API
```

**Proposed:**

```yaml
# sites/sharesight-api.yaml
# id is optional, defaults to "sharesight-api"
name: Sharesight API
```

**Why it's safe:**

- Filename is already used as site identifier in CLI (`web-scraper crawl sharesight-api`)
- Explicit `id` still works (backwards compatible)
- Validation only checks `id` matches filename if `id` is provided
- Snapshot directories still use `config.id` (which now defaults to filename stem)

**Implementation:** Add `@model_validator` to `SiteConfig` that sets `id = filename_stem` if `id` is None.

---

#### Improvement 3: `--chunk` flag on `crawl` command

**Current workflow:**

```bash
$ web-scraper crawl sharesight-api
Snapshot created at corpora/sharesight-api/2025-12-15_0847
$ web-scraper chunk sharesight-api 2025-12-15_0847  # Must copy/paste snapshot ID
```

**Proposed workflow:**

```bash
$ web-scraper crawl sharesight-api --chunk
Snapshot created at corpora/sharesight-api/2025-12-15_0847
Chunks written to corpora/sharesight-api/2025-12-15_0847/chunks.jsonl
```

**Why it's safe:**

- Chunking already operates on completed snapshots
- Flag triggers chunking after successful crawl using the snapshot path the crawler just created
- Doesn't change crawl behaviour, snapshot structure, or chunking logic
- Optional flag (default behaviour unchanged)

**Implementation:** After `scraper.crawl()` succeeds, if `--chunk` flag present, call `chunk_snapshot(snapshot_path, ...)` before returning.

---

#### Improvement 4: Default to resume when incomplete snapshot exists

**Current behaviour:**

```bash
$ web-scraper crawl sharesight-api  # Interrupted at page 8
^C
$ web-scraper crawl sharesight-api  # Starts fresh crawl, ignores incomplete snapshot
$ web-scraper crawl sharesight-api --resume latest  # Must explicitly resume
```

**Proposed behaviour:**

```bash
$ web-scraper crawl sharesight-api  # Interrupted at page 8
^C
$ web-scraper crawl sharesight-api  # Automatically resumes from page 8
Resuming from 2025-12-15_0847: 8 pages completed, 5 pending
$ web-scraper crawl sharesight-api --no-resume  # Force fresh crawl
```

**Why it's safe:**

- Resume logic already exists and works
- Only changes default when `status != completed`
- Adds `--no-resume` flag for escape hatch
- Doesn't change resume behaviour, just makes it default

**Risk:** Users might expect fresh crawl by default. Mitigation: Print clear message when resuming, provide `--no-resume` flag.

---

#### Improvement 5: `init <site-name>` command

**Current workflow:**

```bash
$ cp sites/template.yaml sites/my-site.yaml
$ vim sites/my-site.yaml  # Edit manually
```

**Proposed workflow:**

```bash
$ web-scraper init my-site
Site name: My Site
Entrypoint URL: https://example.com
Include pattern [https://example.com/**]: 
Max pages [100]: 
Created sites/my-site.yaml
```

**Why it's safe:**

- Creates YAML file users would create manually
- Doesn't change YAML requirement or schema
- Validates input using existing `SiteConfig` model
- Pure convenience wrapper around file creation

**Implementation:** Prompt for required fields, write YAML to `sites/{name}.yaml` using template. Validate with `SiteConfig.model_validate()` before writing.

---

### 5.4 What Should NOT Be Fixed

#### 1. Snapshot IDs are timestamps

**Why not:** Automatic generation prevents collisions, provides chronological ordering. Making them user-provided would require collision handling and validation. Timestamps are opaque but predictable.

#### 2. Separate `map` and `crawl` commands

**Why not:** Discovery and execution are conceptually distinct. Combining them would hide the map output, removing the ability to inspect URLs before crawling. Current design allows map → review → crawl workflow.

#### 3. YAML configs instead of CLI arguments

**Why not:** This is foundational. Reproducible crawls require durable configuration. CLI-only scraping would lose versioning, reusability, and configuration management benefits.

#### 4. Filesystem navigation for results

**Why not:** This is foundational. Local-first design means filesystem is the interface. Adding a database or query layer would violate the architecture constraint.

#### 5. No single `scrape` command that takes a URL

**Why not:** Would require either ephemeral configs (violates YAML requirement) or auto-generating YAML files (hidden complexity). Current design makes configuration explicit and durable.

#### 6. Manual format specification in YAML

**Why not:** Explicit control over output formats is intentional. Auto-detecting or defaulting formats would create surprises and make configs less reproducible.

#### 7. Corpus directory structure

**Why not:** Downstream consumers depend on `corpora/{site_id}/{snapshot_id}/manifest.json` contract. Changing this would break all existing integrations.

---

## 6. Summary of Analysis

The current workflow is **coherent and well-architected** for its intended use case (local-first, configuration-driven, snapshot-based website archiving), but it assumes a **specific user profile** (developer, comfortable with CLI/filesystem, wants versioned corpora).

**Key strengths:**

- Immutable snapshots provide strong versioning guarantees
- YAML configs enable reproducible crawls
- Resumable crawls with Ctrl+C safety
- Comprehensive metadata in manifests
- Flexible output formats

**Key friction points:**

- High barrier to entry (YAML config creation)
- Two-step workflows (crawl → chunk, map → crawl)
- No snapshot discovery commands
- Opaque snapshot IDs
- Resume semantics not obvious

**Most clunky elements:**

1. **Filename must match `id` field** (incidental complexity, could be auto-derived)
2. **No `list-snapshots` command** (probably unnecessary, easy to add)
3. **Resume requires explicit flag** (could be smarter default behaviour)

**Most justified elements:**

1. **YAML configs** (intentional, enables reproducibility)
2. **Snapshot-based layout** (intentional, enables versioning)
3. **Separate chunk command** (intentional, keeps crawl focused)

The workflow is **natural for its target users** (developers building LLM corpora) but **clunky for casual users** (who expect "just scrape this URL"). This is an intentional trade-off, not an accident.

**Lowest risk, highest impact improvements:**

1. `list-snapshots` command (pure read operation)
2. Auto-derive `id` from filename (removes redundancy)
3. `init` command (scaffolding convenience)

**Higher risk, but justified improvements:**

4. `--chunk` flag on `crawl` (common workflow optimisation)
5. Default resume behaviour (changes default, but adds escape hatch)

All proposed improvements are **backwards compatible** and **composable**. None require architectural changes or new abstractions.

