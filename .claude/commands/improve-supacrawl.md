# Improve Supacrawl (experiential loop)

A repeatable loop that makes every "improve supacrawl" session **compound** on the last instead of starting cold. The benchmark is the fitness function; the lessons registry is the memory. Run this whenever the operator asks to improve scrape/search quality.

The durable rule: **never "improve" without the benchmark.** Measure, target the weakest real signal, change the root cause, confirm a real lift with no regression, and record what you learned. A defect the bench cannot see is itself a bench gap — close it.

## When to Use

- The operator says "improve supacrawl", "make scraping better", "raise the bench", or names a site that scrapes poorly.
- After a dependency bump or a refactor, to confirm no quality regression.
- Periodically, to chip away at the weakest scored category.

## The Loop

### 1. Read the memory first

Read [`docs/development/improvement-lessons.md`](../../docs/development/improvement-lessons.md) end to end. Note the open threads, what was already tried, and the section **"What the bench can and cannot see"** — do not trust a score you have not understood. The product-facing half of the self-improvement story (supacrawl learning per-domain in the field) is the `adaptive` module at `docs/product/features/adaptive/`; this loop makes the _tool_ better release over release.

### 2. Measure (the fitness function)

```bash
uv run supacrawl bench run                  # overall score, per-category, worst scored cases
uv run supacrawl bench list                 # find the previous run id
uv run supacrawl bench compare <prev> <new> # catch regressions vs the last run
```

Record the overall scored score, the per-category breakdown, and the worst-scoring **scored** cases. Ignore `scored: false` capability probes for the headline number, but read their reference-free signals (`expect_hit`, `word_spacing`, structure) — those are trustworthy everywhere.

### 3. Target

Pick **one** of:

- the weakest scored category or case from step 2, or
- a real-world gap. Drive the CLI and the `browser-driver` MCP against the operator's matrix: **Amazon, Qantas, hotels, ATO gov tax-law (RAG), a SERP query, pet food**. Read the new `quality` verdict on each result (`result.quality.verdict` / `.score`) — a `bot_challenge`, `js_shell`, `thin`, or `empty` verdict on a site that should work is a target.

Delegate the breadth-first probing of the matrix to a tightly-scoped sub-agent (no recursive fan-out, return a compact table of `url → verdict/score/words`); keep the judgement (which case to fix) in the main session. Do **not** fire an opaque long-running research agent — scope it or run it in the background with a heartbeat (a stalled 13-minute agent is the #131 anti-pattern).

### 4. Change

Make the **smallest change that should move the metric**, fixing a root cause over a special-case. The codebase already gives you the levers:

- Poor verdict on defaults → is the `#129` escalation ladder reaching far enough? (`services/scrape.py` `_next_escalation`.)
- Garbled / thin extraction → `services/converter.py`, `services/content_filter.py`, the `#129` thin-content fallback, or `services/pdf.py`.
- Wrong quality verdict → `supacrawl/quality.py` (`assess_quality`, the shared metric vocabulary the bench also consumes).
- Search returns nothing → `services/search/`.

### 5. Confirm

Re-run `bench run` and `bench compare` against the pre-change run. The targeted case's score **must rise** and nothing else may regress. The non-e2e suite must stay green:

```bash
uv run pytest -q -m "not e2e"
uv run ruff check src tests && uv run mypy src
```

### 6. Sharpen the bench when it is blind

If a defect you fixed (or found) does **not** move any bench metric, the bench has a blind spot. Add a probe or metric so the fitness function can see that class of defect next time (a reference-free metric in `supacrawl/quality.py` + a corpus anchor in `benchmark/corpus/default.yaml`, with its own pytest). This is how the bench gets sharper — it is part of the work, not optional.

### 7. Record

Append a dated entry to [`docs/development/improvement-lessons.md`](../../docs/development/improvement-lessons.md) using the existing format: **Did / Worked / Surprised / Open threads**. Be specific about what moved the metric and what surprised you — that is the memory the next session reads first.

## Done When

The repo is left with: improved code, an updated bench baseline (a fresh run committed or referenced), a green non-e2e suite, and a new lessons entry. Every run leaves the tool measurably better and the next run better-informed — that is the compounding effect this loop exists to create.
