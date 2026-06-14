"""Optional LLM-as-judge for benchmark case quality assessment.

The judge compares supacrawl's markdown output against the browser reference
text and returns a 0-100 quality score plus a rationale. It is intentionally
optional: if no LLM is configured, or if the provider call fails for any
reason, the judge returns ``(None, None)`` so the overall run always completes.
"""

from __future__ import annotations

import logging

from supacrawl.benchmark.models import BenchCase

LOGGER = logging.getLogger(__name__)

# Character limit applied to each input before sending to the LLM. Keeps
# the prompt within a reasonable token budget while covering article-length
# content.
_MAX_INPUT_CHARS = 6000

_SYSTEM_PROMPT = """\
You are an expert evaluator of web-scraping quality.
You will be given two pieces of text:

1. REFERENCE: the ground-truth text a real browser extracted from a web page.
2. EXTRACTED: the markdown that a web scraper produced for the same page.

Score the extracted content on a 0-100 scale judging:
- Completeness: how much of the reference content is present.
- Noise: how much irrelevant content (navigation, ads, chrome) leaked in.
- Formatting fidelity: whether headings, code blocks, and lists are preserved.

Return ONLY a JSON object with two keys: "score" (integer 0-100) and
"rationale" (one concise sentence explaining the score)."""


async def judge_case(
    *,
    case: BenchCase,
    markdown: str,
    reference_text: str | None,
) -> tuple[float | None, str | None]:
    """Score a scraped case with an LLM judge.

    When no LLM is configured or the provider call fails for any reason,
    returns ``(None, None)`` so the calling runner can continue without
    interruption. Inputs are truncated to ``_MAX_INPUT_CHARS`` to stay within
    a sensible token budget.

    Args:
        case: The benchmark case being evaluated (used for logging context).
        markdown: The scraper's markdown output to evaluate.
        reference_text: Ground-truth text from the browser reference, or
            ``None`` when unavailable (e.g. PDF cases without capture).

    Returns:
        ``(score, rationale)`` where score is in ``[0, 100]``, or
        ``(None, None)`` when the judge cannot run.
    """
    from supacrawl.llm.config import is_llm_configured

    if not is_llm_configured():
        return None, None

    if not reference_text:
        # Without a reference there is nothing meaningful to compare against.
        return None, None

    try:
        from supacrawl.llm import LLMClient, load_llm_config

        client = LLMClient(load_llm_config())
        try:
            ref_excerpt = reference_text[:_MAX_INPUT_CHARS]
            ext_excerpt = markdown[:_MAX_INPUT_CHARS]

            user_content = f"REFERENCE:\n{ref_excerpt}\n\nEXTRACTED:\n{ext_excerpt}"
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            data = await client.chat_json(messages)
            score_raw = data.get("score")
            rationale = data.get("rationale")

            if score_raw is None:
                return None, None

            score = float(score_raw)
            score = max(0.0, min(100.0, score))
            return score, str(rationale) if rationale else None

        finally:
            await client.close()

    except Exception as exc:
        LOGGER.debug("LLM judge failed for case %s: %s", case.id, exc)
        return None, None
