"""Reference-based scoring functions for the scrape-quality benchmark.

Every function here is deterministic and side-effect free: given the same text
it returns the same numbers, which is what makes run-over-run comparison valid.
Nothing in this module performs I/O, touches the network, or imports a browser.

These are the metrics that compare the scraper's output against an independent
browser capture (the "gold" reference): token-overlap F1 in the SQuAD sense,
ROUGE-L longest-common-subsequence, and a language-agnostic character-coverage
proxy. The *reference-free* primitives (tokenisation, word-spacing, link
density, structure counts, anchor hit rates) live in ``supacrawl.quality`` so
the live runtime quality assessor and this offline benchmark share one
definition of "good".
"""

from __future__ import annotations

from collections import Counter

# ROUGE-L runs an O(n*m) dynamic program; cap the sequences it sees so a very
# long page cannot make a run pathologically slow. The cap is generous enough to
# cover article-length content.
_ROUGE_TOKEN_CAP = 4000


def token_prf(extracted: list[str], gold: list[str]) -> tuple[float, float, float]:
    """Bag-of-words precision, recall and F1 in the SQuAD sense.

    Overlap is the multiset intersection: each token counts up to the number of
    times it appears in *both* sequences, so padding the extraction with extra
    copies of a gold word cannot inflate recall.

    Args:
        extracted: Tokens from the scraper output.
        gold: Tokens from the reference main text.

    Returns:
        ``(precision, recall, f1)``, each in ``[0, 1]``. All zero when either
        side is empty.
    """
    if not extracted or not gold:
        return 0.0, 0.0, 0.0
    extracted_counts = Counter(extracted)
    gold_counts = Counter(gold)
    overlap = sum((extracted_counts & gold_counts).values())
    if overlap == 0:
        return 0.0, 0.0, 0.0
    precision = overlap / len(extracted)
    recall = overlap / len(gold)
    f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def rouge_l(extracted: list[str], gold: list[str]) -> float:
    """ROUGE-L F-measure over token sequences.

    Uses the longest common subsequence, which rewards preserving the *order* of
    the reference content, not merely its vocabulary. Both sequences are capped
    to bound the dynamic program's cost on very long pages.

    Args:
        extracted: Tokens from the scraper output.
        gold: Tokens from the reference main text.

    Returns:
        F-measure in ``[0, 1]``; 0 when either side is empty.
    """
    if not extracted or not gold:
        return 0.0
    a = extracted[:_ROUGE_TOKEN_CAP]
    b = gold[:_ROUGE_TOKEN_CAP]
    lcs = _lcs_length(a, b)
    if lcs == 0:
        return 0.0
    precision = lcs / len(a)
    recall = lcs / len(b)
    return 2 * precision * recall / (precision + recall)


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Length of the longest common subsequence of two token lists.

    Uses a rolling two-row table so memory stays linear in the shorter list.

    Args:
        a: First token list.
        b: Second token list.

    Returns:
        LCS length.
    """
    if len(b) > len(a):
        a, b = b, a
    previous = [0] * (len(b) + 1)
    for token_a in a:
        current = [0] * (len(b) + 1)
        for j, token_b in enumerate(b, start=1):
            if token_a == token_b:
                current[j] = previous[j - 1] + 1
            else:
                current[j] = max(previous[j], current[j - 1])
        previous = current
    return previous[len(b)]


def char_coverage(extracted_chars: int, reference_chars: int) -> float:
    """Completeness as a ratio of visible character counts, clamped to 1.

    A language-agnostic proxy for "did we capture most of the real content?"
    that does not depend on word tokenisation, so it stays meaningful for CJK
    and other non-whitespace-delimited scripts. Values above 1 (the scraper
    emitted more characters than the reference, usually leaked chrome) are
    clamped, because over-capture is penalised through noise, not coverage.

    Args:
        extracted_chars: Visible character count of the scraper output.
        reference_chars: Visible character count of the browser reference.

    Returns:
        Ratio in ``[0, 1]``; 0 when the reference is empty.
    """
    if reference_chars <= 0:
        return 0.0
    return min(1.0, extracted_chars / reference_chars)


# Minimum reference size (words) below which the reference renderer is assumed to
# have under-captured rather than the page being genuinely short. Paired with the
# ratio test below so a genuinely tiny page (output and reference both small and
# in agreement) is still scored against its reference.
REFERENCE_DEGENERATE_WORD_FLOOR = 50
# Output-to-reference word ratio above which — combined with a tiny reference —
# the reference is treated as degenerate: the scrape extracted far more than the
# reference captured, so the reference renderer, not the scrape, is the outlier.
REFERENCE_DEGENERATE_RATIO = 3.0


def reference_is_degenerate(markdown_words: int, reference_words: int | None) -> bool:
    """Whether the reference capture is too thin to trust for reference-based metrics.

    The independent reference renderer (vanilla headless Chromium, no stealth)
    intermittently captures only a shell on JS-hydrated or lightly bot-protected
    pages. When it does, ``token_f1`` and ``noise`` — which compare the scrape
    against that shell — punish a correct, fuller extraction for content the
    reference simply missed. This predicate detects that case so the caller can
    fall back to the reference-free signals (anchors, structure, spacing).

    A reference is degenerate when it is small in absolute terms AND the scrape
    extracted substantially more, which together indicate the reference
    under-captured rather than the page being genuinely short (where output and
    reference are both small and agree).

    Args:
        markdown_words: Word count of the scrape's markdown output.
        reference_words: Word count of the reference capture, or ``None``.

    Returns:
        ``True`` when reference-based metrics should be discarded for this case.
    """
    if reference_words is None:
        return False
    if reference_words >= REFERENCE_DEGENERATE_WORD_FLOOR:
        return False
    return markdown_words > reference_words * REFERENCE_DEGENERATE_RATIO


def composite_quality(
    *,
    success: bool,
    char_coverage_value: float | None,
    token_f1: float | None,
    noise: float | None,
    expect_hit: float | None,
    expect_absent_ok: float | None,
    link_density_value: float | None,
    word_spacing_value: float | None = None,
) -> float:
    """Blend the per-case signals into a single 0-100 quality score.

    The weighting favours completeness (did we keep the real content?) and
    fidelity (token F1, which penalises both misses and noise), then layers the
    curated anchors and a light link-density penalty on top. Each component is
    skipped gracefully when its input is ``None`` and the remaining weights are
    renormalised, so a page with no reference still scores on whatever signal is
    available. A failed scrape scores 0.

    Args:
        success: Whether the scrape returned content.
        char_coverage_value: Language-agnostic completeness ratio.
        token_f1: Bag-of-words F1 against the reference.
        noise: Fraction of output tokens absent from the reference (penalised).
        expect_hit: Fraction of gold anchors present.
        expect_absent_ok: Fraction of boilerplate anchors correctly absent.
        link_density_value: Links per 1000 words (penalised above a threshold).
        word_spacing_value: Inter-word spacing sanity (catches fused PDF text).

    Returns:
        Composite score in ``[0, 100]``.
    """
    if not success:
        return 0.0

    components: list[tuple[float, float]] = []  # (weight, value in [0, 1])

    if char_coverage_value is not None:
        components.append((0.30, char_coverage_value))
    if token_f1 is not None:
        components.append((0.25, token_f1))
    if expect_hit is not None:
        components.append((0.15, expect_hit))
    if noise is not None:
        components.append((0.15, 1.0 - noise))
    if expect_absent_ok is not None:
        components.append((0.10, expect_absent_ok))
    if link_density_value is not None:
        # 0 links/1k words is ideal; 50+ is menu-grade noise. Linear penalty.
        components.append((0.05, max(0.0, 1.0 - link_density_value / 50.0)))
    if word_spacing_value is not None:
        # Fused word runs (a PDF spacing defect) make output near-useless for RAG
        # even when the right anchors are present; weight it alongside the anchors.
        components.append((0.10, word_spacing_value))

    if not components:
        # Nothing to score on but the scrape succeeded; give a neutral floor.
        return 50.0

    total_weight = sum(weight for weight, _ in components)
    score = sum(weight * value for weight, value in components) / total_weight
    return round(100.0 * score, 1)
