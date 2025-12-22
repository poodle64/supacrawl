# Phase 0: Stated Goals (Repo Evidence)

## Claims Table

| Claim | Source | Line/Section | Implication for Tests/Parity |
|-------|--------|--------------|------------------------------|
| "Think Firecrawl's output format and quality, but running entirely on your machine" | README.md | Line 5 | Must verify output format compatibility (markdown, manifest structure) and quality parity |
| "produces **similar output** to Firecrawl (markdown, structured manifests, LLM-ready chunks)" | README.md | Line 27 | Must compare markdown content quality, manifest schema, chunk format |
| "**Not a SaaS replacement**" | README.md | Line 18 (explicit negative claim) | NOT claiming API endpoint compatibility or service replacement |
| "**different deployment model**" (comparison table) | README.md | Lines 29-37 | Different architecture (local CLI vs hosted SaaS), not claiming API parity |
| "Similar output format" | README.md | Line 27 | Output format compatibility only, not behavioral parity |
| Parity testing infrastructure exists | tools/parity/ | Multiple files | Indicates active quality benchmarking against Firecrawl |
| Parity report shows 77.3% avg similarity (baseline) | docs/parity/parity-report.md | Lines 20-22 | Establishes baseline quality score vs Firecrawl |
| "Uses Firecrawl as a **quality benchmark**, not a competitor" | Analysis of README tone | Lines 25-42 | Positioning: complementary tool, not replacement |

## Summary of Stated Goals

### What the Repo Claims

1. **Output Format Similarity**: Produces markdown, HTML, manifests, and chunks in a format similar to Firecrawl
2. **Quality Target**: Aims for Firecrawl-level quality in content extraction
3. **Different Use Case**: Local-first, periodic corpus building vs on-demand SaaS scraping
4. **Not a Replacement**: Explicitly states "Not a SaaS replacement" (line 18)
5. **Complementary Tool**: Different deployment model for different use cases

### What the Repo Does NOT Claim

1. **API Compatibility**: No claim of drop-in API endpoint replacement
2. **Service Parity**: No claim of matching Firecrawl's SaaS service features
3. **Behavioral Equivalence**: No claim of identical behavior, only similar output
4. **Superiority**: Uses Firecrawl as benchmark, not claiming to be better
5. **Complete Feature Parity**: Comparison table shows deliberate differences

## Implications for Audit

### Primary Test Focus
1. **Output Format Compatibility**: Verify markdown, manifest, chunks follow similar structure
2. **Quality Comparison**: Measure content quality vs Firecrawl using parity metrics
3. **Unique Value**: Assess local-first, snapshot-based, versioned corpus features

### NOT Testing For
1. API endpoint compatibility (not claimed)
2. SaaS service features (explicitly disclaimed)
3. Real-time scraping (designed for periodic crawls)
4. Multi-tenancy or hosted features (local-only)

### Audit Question Reframing

**Original Question**: "Is this a drop-in replacement for Firecrawl?"
**Answer Based on Repo Evidence**: **NO** - Repo explicitly disclaims being a SaaS replacement

**Correct Audit Question**: "Does this repo deliver on its stated goal of Firecrawl-quality output in a local-first deployment model?"

### Parity Testing Focus

1. **Output Format**: Markdown structure, manifest schema, chunk format
2. **Content Quality**: Text extraction completeness, link preservation, metadata richness
3. **Quality Benchmarking**: Compare against Firecrawl using similarity metrics (already done, 77.3% baseline)
4. **Unique Features**: Snapshot versioning, resumable crawls, corpus layout
5. **Safety/Correctness**: No duplicate outputs, correct URL-to-file mapping, checksum integrity

## Verdict on "Drop-in Replacement" Claim

**Status**: **CLAIM NOT MADE**

The repository **explicitly disclaims** being a Firecrawl replacement:
- Line 18: "**Not a SaaS replacement**"
- Lines 29-37: Comparison table shows different deployment model
- Line 27: Claims "similar output", not "identical service"
- Tone: Respectful comparison, uses Firecrawl as quality benchmark

**Recommendation**: Audit should focus on verifying stated goals (output quality, format similarity, unique local-first features) rather than testing for unstated claims (API compatibility, service parity).
