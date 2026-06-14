"""Benchmark runner — orchestrates a full benchmark run over a suite.

Accepts a ``BenchSuite``, drives each case through the provider and optionally
the browser reference renderer, scores every metric, and returns a ``RunResult``
with per-case detail and a run-level aggregate.

Concurrency is throttled via an ``asyncio.Semaphore`` because browser pages are
memory-heavy; the default is intentionally conservative.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from supacrawl.benchmark.judge import judge_case
from supacrawl.benchmark.metrics import (
    char_coverage,
    composite_quality,
    count_structure,
    link_density,
    rouge_l,
    strip_markdown,
    substring_absent_rate,
    substring_hit_rate,
    token_prf,
    tokenize,
)
from supacrawl.benchmark.models import (
    BenchCase,
    BenchSuite,
    CaseMetrics,
    CaseResult,
    RunAggregate,
    RunResult,
)
from supacrawl.benchmark.providers.base import ProviderOutput, ScraperProvider
from supacrawl.benchmark.providers.supacrawl import SupacrawlProvider
from supacrawl.benchmark.reference import ReferenceCapture, ReferenceRenderer

LOGGER = logging.getLogger(__name__)


def _git_sha() -> str | None:
    """Return the short HEAD SHA for the current repo, or None on failure.

    Returns:
        8-character SHA string, or ``None`` if git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _run_id(sha: str | None) -> str:
    """Build a compact run ID from the current UTC time and git SHA.

    Args:
        sha: Short git SHA or ``None``.

    Returns:
        String like ``"20260614T083012-a1b2c3d4"`` or ``"20260614T083012"`` when
        no SHA is available.
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{ts}-{sha}" if sha else ts


def _score_case(
    *,
    case: BenchCase,
    output: ProviderOutput,
    reference: ReferenceCapture | None,
    judge_score: float | None,
    judge_rationale: str | None,
) -> CaseMetrics:
    """Compute all metrics for a single case result.

    Args:
        case: The benchmark case definition.
        output: Normalised scraper output for this case.
        reference: Browser ground-truth capture, or ``None`` for PDFs/failures.
        judge_score: LLM judge score in ``[0, 100]``, or ``None``.
        judge_rationale: LLM judge rationale string, or ``None``.

    Returns:
        Fully populated ``CaseMetrics``.
    """
    markdown = output.markdown or ""
    plain_text = strip_markdown(markdown)

    md_words = len(tokenize(markdown, markdown=True))
    md_chars = len(plain_text)

    # Anchor-based metrics — always available when the case has anchors
    expect_hit = substring_hit_rate(markdown, case.expect)
    expect_absent_ok = substring_absent_rate(markdown, case.expect_absent)

    # Structure in the produced markdown
    structure = count_structure(markdown)
    ld = link_density(structure["links"], md_words)

    # Reference-based metrics — only when the reference was captured and
    # the scrape succeeded; for PDFs and failed references these stay None.
    char_cov: float | None = None
    token_f1: float | None = None
    rouge_l_val: float | None = None
    noise: float | None = None
    ref_chars: int | None = None
    ref_words: int | None = None

    if output.success and reference and not reference.error and case.content_type != "pdf":
        ref_text = reference.main_text or ""
        ref_chars = len(ref_text)
        ref_words = len(tokenize(ref_text))

        char_cov = char_coverage(md_chars, ref_chars)

        ext_tokens = tokenize(plain_text)
        gold_tokens = tokenize(ref_text)
        _, _, f1 = token_prf(ext_tokens, gold_tokens)
        token_f1 = f1
        rouge_l_val = rouge_l(ext_tokens, gold_tokens)

        # Noise = fraction of extracted tokens absent from the reference.
        # We compute 1 - precision from token_prf (precision IS the non-noise).
        precision, _, _ = token_prf(ext_tokens, gold_tokens)
        noise = 1.0 - precision if ext_tokens else None

    quality = composite_quality(
        success=output.success,
        char_coverage_value=char_cov,
        token_f1=token_f1,
        noise=noise,
        expect_hit=expect_hit,
        expect_absent_ok=expect_absent_ok,
        link_density_value=ld if output.success else None,
    )

    return CaseMetrics(
        success=output.success,
        status_code=output.status_code,
        error=output.error,
        latency_ms=output.latency_ms,
        markdown_chars=md_chars,
        markdown_words=md_words,
        reference_chars=ref_chars,
        reference_words=ref_words,
        char_coverage=char_cov,
        token_f1=token_f1,
        rouge_l=rouge_l_val,
        noise=noise,
        link_density=ld if output.success else None,
        headings=structure["headings"],
        code_blocks=structure["code_blocks"],
        tables=structure["tables"],
        images=structure["images"],
        links=structure["links"],
        json_ld_found=output.json_ld_found,
        expect_hit=expect_hit,
        expect_absent_ok=expect_absent_ok,
        judge_score=judge_score,
        judge_rationale=judge_rationale,
        quality=quality,
    )


def _save_artifacts(
    *,
    case: BenchCase,
    output: ProviderOutput,
    reference: ReferenceCapture | None,
    run_dir: Path,
) -> dict[str, str]:
    """Persist per-case artefacts to disk and return their relative paths.

    Args:
        case: The benchmark case.
        output: Scraper output for this case.
        reference: Browser reference capture, or ``None``.
        run_dir: Directory for this run's artefacts.

    Returns:
        Dict mapping artefact role to path relative to ``run_dir``.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    if output.markdown:
        md_path = run_dir / f"{case.id}.md"
        md_path.write_text(output.markdown, encoding="utf-8")
        artifacts["markdown"] = md_path.name

    if reference:
        if reference.main_text:
            ref_path = run_dir / f"{case.id}.reference.txt"
            ref_path.write_text(reference.main_text, encoding="utf-8")
            artifacts["reference_text"] = ref_path.name

        if reference.screenshot_b64:
            import base64

            ss_path = run_dir / f"{case.id}.screenshot.jpg"
            ss_path.write_bytes(base64.b64decode(reference.screenshot_b64))
            artifacts["screenshot"] = ss_path.name

    return artifacts


async def _run_case(
    *,
    case: BenchCase,
    provider: ScraperProvider,
    renderer: ReferenceRenderer | None,
    judge: bool,
    semaphore: asyncio.Semaphore,
    run_dir: Path,
) -> CaseResult:
    """Run the benchmark for a single case.

    Args:
        case: The benchmark case to run.
        provider: Scraper provider to use.
        renderer: Browser reference renderer, or ``None`` (skips reference).
        judge: Whether to run the LLM judge.
        semaphore: Concurrency guard.
        run_dir: Directory for this run's artefacts.

    Returns:
        ``CaseResult`` with metrics and artefact paths.
    """
    async with semaphore:
        LOGGER.info("Running case: %s (%s)", case.id, case.url)

        output = await provider.scrape(case.url, content_type=case.content_type)

        reference: ReferenceCapture | None = None
        if renderer and case.content_type == "html":
            reference = await renderer.capture(case.url)

        judge_score: float | None = None
        judge_rationale: str | None = None
        if judge and output.success:
            ref_text = reference.main_text if (reference and not reference.error) else None
            judge_score, judge_rationale = await judge_case(
                case=case,
                markdown=output.markdown,
                reference_text=ref_text,
            )

        metrics = _score_case(
            case=case,
            output=output,
            reference=reference,
            judge_score=judge_score,
            judge_rationale=judge_rationale,
        )

        artifacts = _save_artifacts(
            case=case,
            output=output,
            reference=reference,
            run_dir=run_dir,
        )

        return CaseResult(
            case_id=case.id,
            category=case.category,
            url=case.url,
            difficulty=case.difficulty,
            scored=case.is_scored,
            metrics=metrics,
            artifacts=artifacts,
        )


def _build_aggregate(results: list[CaseResult]) -> RunAggregate:
    """Build the run-level aggregate from all case results.

    Args:
        results: All case results from the run.

    Returns:
        ``RunAggregate`` with overall and per-category rollups.
    """
    total = len(results)
    succeeded = sum(1 for r in results if r.metrics.success)
    success_rate = succeeded / total if total else 0.0

    latencies = [r.metrics.latency_ms for r in results if r.metrics.latency_ms is not None]
    mean_latency = sum(latencies) / len(latencies) if latencies else None

    scored = [r for r in results if r.scored and r.metrics.quality is not None]
    scored_count = len(scored)
    overall_quality: float | None = None
    if scored:
        scored_qualities: list[float] = [r.metrics.quality for r in scored]  # type: ignore[misc]
        overall_quality = round(sum(scored_qualities) / scored_count, 1)

    # Per-category means over scored cases only
    by_category: dict[str, float] = {}
    categories: set[str] = {r.category for r in results}
    for cat in categories:
        cat_scored = [r for r in scored if r.category == cat]
        if cat_scored:
            cat_qualities: list[float] = [r.metrics.quality for r in cat_scored]  # type: ignore[misc]
            by_category[cat] = round(sum(cat_qualities) / len(cat_scored), 1)

    return RunAggregate(
        overall_quality=overall_quality,
        by_category=by_category,
        total_cases=total,
        scored_cases=scored_count,
        success_rate=success_rate,
        mean_latency_ms=mean_latency,
    )


async def run_benchmark(
    suite: BenchSuite,
    *,
    judge: bool = False,
    concurrency: int = 3,
    base_dir: Path,
    only: list[str] | None = None,
) -> RunResult:
    """Run the full benchmark over ``suite`` and return results.

    Cases are filtered by ``only`` (matching case id OR category, case-
    insensitive) when provided. The browser reference renderer is constructed
    once and shared across all HTML cases.

    Args:
        suite: The benchmark suite to run.
        judge: Whether to invoke the LLM judge on each scored case.
        concurrency: Maximum number of cases running in parallel.
        base_dir: Root directory for artefact storage; artefacts land in
            ``base_dir/runs/<run_id>/<case_id>.*``.
        only: Optional list of case IDs or category names to restrict the run.
            When ``None``, all cases are run.

    Returns:
        ``RunResult`` with all case results and the run aggregate.
    """
    from importlib.metadata import version as pkg_version

    started_at = datetime.now(UTC).isoformat()
    sha = _git_sha()
    run_id = _run_id(sha)

    try:
        supacrawl_version = pkg_version("supacrawl")
    except Exception:
        supacrawl_version = "unknown"

    # Filter cases
    cases = suite.cases
    if only:
        only_lower = {o.lower() for o in only}
        cases = [c for c in cases if c.id.lower() in only_lower or c.category.lower() in only_lower]

    run_dir = base_dir / "runs" / run_id
    semaphore = asyncio.Semaphore(concurrency)

    provider: ScraperProvider = SupacrawlProvider()
    try:
        async with ReferenceRenderer() as renderer:
            tasks = [
                _run_case(
                    case=case,
                    provider=provider,
                    renderer=renderer,
                    judge=judge,
                    semaphore=semaphore,
                    run_dir=run_dir,
                )
                for case in cases
            ]
            case_results = await asyncio.gather(*tasks)
    finally:
        await provider.aclose()

    results = list(case_results)
    aggregate = _build_aggregate(results)

    finished_at = datetime.now(UTC).isoformat()

    return RunResult(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        supacrawl_version=supacrawl_version,
        git_sha=sha,
        provider=provider.name,
        judge_enabled=judge,
        suite_name=suite.name,
        cases=results,
        aggregate=aggregate,
    )
