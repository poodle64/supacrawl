"""Report generation for parity comparison results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_json_report(results: dict[str, Any], output_path: Path) -> None:
    """
    Generate JSON report with all metrics.

    Args:
        results: Complete comparison results.
        output_path: Path to write JSON report.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)


def generate_markdown_report(results: dict[str, Any], output_path: Path) -> None:
    """
    Generate human-readable markdown report.

    Args:
        results: Complete comparison results.
        output_path: Path to write markdown report.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Firecrawl Parity Comparison Report")
    lines.append("")
    lines.append(f"**Generated:** {results['timestamp']}")
    lines.append(f"**URLs Tested:** {results['urls_tested']}")
    lines.append("")

    # Aggregate summary
    aggregate = results["aggregate"]
    lines.append("## Aggregate Summary")
    lines.append("")
    lines.append("### Success Rates")
    lines.append("")
    lines.append("| System | Success Rate |")
    lines.append("|--------|--------------|")
    lines.append(
        f"| Firecrawl | {aggregate['success_rates']['firecrawl'] * 100:.1f}% |"
    )
    lines.append(
        f"| Baseline-Static | {aggregate['success_rates']['baseline_static'] * 100:.1f}% |"
    )
    lines.append(
        f"| Enhanced | {aggregate['success_rates']['enhanced'] * 100:.1f}% |"
    )
    lines.append("")

    lines.append("### Average Similarity Scores")
    lines.append("")
    lines.append("| Comparison | Similarity |")
    lines.append("|-----------|-----------|")
    lines.append(
        f"| Firecrawl vs Baseline-Static | {aggregate['avg_similarity']['firecrawl_vs_baseline']:.3f} |"
    )
    lines.append(
        f"| Firecrawl vs Enhanced | {aggregate['avg_similarity']['firecrawl_vs_enhanced']:.3f} |"
    )
    lines.append(
        f"| Baseline-Static vs Enhanced | {aggregate['avg_similarity']['baseline_vs_enhanced']:.3f} |"
    )
    lines.append("")

    # Per-URL comparison table
    lines.append("## Per-URL Comparison")
    lines.append("")
    lines.append(
        "| URL | Firecrawl | Baseline | Enhanced | F vs B | F vs E | B vs E |"
    )
    lines.append("|-----|-----------|----------|----------|--------|--------|--------|")

    for result in results["results"]:
        url = result["url"]
        # Truncate long URLs for table
        url_display = url[:50] + "..." if len(url) > 50 else url

        firecrawl_success = "✓" if result["firecrawl"]["success"] else "✗"
        baseline_success = "✓" if result["baseline_static"]["success"] else "✗"
        enhanced_success = "✓" if result["enhanced"]["success"] else "✗"

        similarity = result.get("similarity", {})
        f_vs_b = f"{similarity.get('firecrawl_vs_baseline', 0.0):.3f}" if similarity else "N/A"
        f_vs_e = f"{similarity.get('firecrawl_vs_enhanced', 0.0):.3f}" if similarity else "N/A"
        b_vs_e = f"{similarity.get('baseline_vs_enhanced', 0.0):.3f}" if similarity else "N/A"

        lines.append(
            f"| {url_display} | {firecrawl_success} | {baseline_success} | {enhanced_success} | {f_vs_b} | {f_vs_e} | {b_vs_e} |"
        )

    lines.append("")

    # Detailed metrics per URL
    lines.append("## Detailed Metrics")
    lines.append("")
    for result in results["results"]:
        lines.append(f"### {result['url']}")
        lines.append("")

        # Firecrawl metrics
        if result["firecrawl"]["success"]:
            lines.append("**Firecrawl:**")
            metrics = result["firecrawl"]["metrics"]
            lines.append(f"- Characters: {metrics.get('char_count', 0):,}")
            lines.append(f"- Words: {metrics.get('word_count', 0):,}")
            lines.append(f"- Links: {metrics.get('link_count', 0)}")
            lines.append(f"- Links missing text: {metrics.get('links_missing_text', 0)}")
            lines.append(f"- Headings: {metrics.get('heading_total', 0)}")
            lines.append(f"- Code blocks: {metrics.get('code_blocks_fenced', 0)}")
            lines.append(f"- Tables: {metrics.get('table_count', 0)}")
            lines.append("")

        # Baseline metrics
        if result["baseline_static"]["success"]:
            lines.append("**Baseline-Static:**")
            metrics = result["baseline_static"]["metrics"]
            lines.append(f"- Characters: {metrics.get('char_count', 0):,}")
            lines.append(f"- Words: {metrics.get('word_count', 0):,}")
            lines.append(f"- Links: {metrics.get('link_count', 0)}")
            lines.append(f"- Links missing text: {metrics.get('links_missing_text', 0)}")
            lines.append(f"- Headings: {metrics.get('heading_total', 0)}")
            lines.append(f"- Code blocks: {metrics.get('code_blocks_fenced', 0)}")
            lines.append(f"- Tables: {metrics.get('table_count', 0)}")
            lines.append("")

        # Enhanced metrics
        if result["enhanced"]["success"]:
            lines.append("**Enhanced:**")
            metrics = result["enhanced"]["metrics"]
            lines.append(f"- Characters: {metrics.get('char_count', 0):,}")
            lines.append(f"- Words: {metrics.get('word_count', 0):,}")
            lines.append(f"- Links: {metrics.get('link_count', 0)}")
            lines.append(f"- Links missing text: {metrics.get('links_missing_text', 0)}")
            lines.append(f"- Headings: {metrics.get('heading_total', 0)}")
            lines.append(f"- Code blocks: {metrics.get('code_blocks_fenced', 0)}")
            lines.append(f"- Tables: {metrics.get('table_count', 0)}")
            lines.append("")

    # Decision gate
    decision = results["decision"]
    lines.append("## Decision Gate")
    lines.append("")
    lines.append(f"**Recommendation:** {decision['recommendation']}")
    lines.append("")
    lines.append(f"**Reason:** {decision['reason']}")
    lines.append("")

    lines.append("### Decision Metrics")
    lines.append("")
    decision_metrics = decision["metrics"]
    lines.append(f"- Firecrawl vs Baseline-Static similarity: {decision_metrics['firecrawl_vs_baseline_similarity']:.3f}")
    lines.append(f"- Firecrawl vs Enhanced similarity: {decision_metrics['firecrawl_vs_enhanced_similarity']:.3f}")
    lines.append(f"- Similarity improvement: {decision_metrics['similarity_improvement'] * 100:+.1f}%")
    lines.append(f"- Baseline success rate: {decision_metrics['baseline_success_rate'] * 100:.1f}%")
    lines.append(f"- Enhanced success rate: {decision_metrics['enhanced_success_rate'] * 100:.1f}%")
    lines.append(f"- Success rate improvement: {decision_metrics['success_rate_improvement'] * 100:+.1f}%")
    lines.append("")

    if decision["recommendation"] == "KEEP":
        lines.append("### Next Steps (if KEEP)")
        lines.append("")
        lines.append("- Collapse fixes behind a single internal postprocess flag")
        lines.append("- Remove plugin UX and list-fixes command")
        lines.append("- Keep minimal postprocess layer")
        lines.append("")
    else:
        lines.append("### Next Steps (if REMOVE)")
        lines.append("")
        lines.append("- Delete plugin registry (`web_scraper/content/fixes/`)")
        lines.append("- Remove `list-fixes` CLI command")
        lines.append("- Remove `markdown_fixes` YAML config section")
        lines.append("- Remove related documentation")
        lines.append("")

    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

