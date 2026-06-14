"""Pure scoring functions for the scrape-quality benchmark.

Every function here is deterministic and side-effect free: given the same text
it returns the same numbers, which is what makes run-over-run comparison valid.
Nothing in this module performs I/O, touches the network, or imports a browser.

The metric vocabulary draws on established main-content-extraction benchmarks
(token-overlap F1 in the SQuAD sense, ROUGE-L longest-common-subsequence) plus a
language-agnostic character-coverage proxy so that non-Latin pages, where
whitespace tokenisation breaks down, still yield a meaningful completeness
signal.
"""

from __future__ import annotations

import re
from collections import Counter

# ROUGE-L runs an O(n*m) dynamic program; cap the sequences it sees so a very
# long page cannot make a run pathologically slow. The cap is generous enough to
# cover article-length content.
_ROUGE_TOKEN_CAP = 4000

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Markdown syntax stripped before tokenising so that formatting characters do
# not masquerade as content tokens.
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_CODE_FENCE_RE = re.compile(r"```[^\n]*")
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)

# Structure counters operate on raw markdown.
_HEADING_LINE_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s{0,3}```", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s{0,3}\|.*\|\s*$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"(?<!\!)\[[^\]]*\]\([^)]*\)")


def strip_markdown(text: str) -> str:
    """Reduce markdown to its visible prose for tokenising.

    Images are dropped entirely, links collapse to their anchor text, and code
    fence markers and heading hashes are removed. The result is not meant to be
    read; it is an intermediate for word tokenisation.

    Args:
        text: Markdown source.

    Returns:
        Plain-ish text with markdown scaffolding removed.
    """
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_CODE_FENCE_RE.sub(" ", text)
    text = _MD_HEADING_RE.sub("", text)
    return text


def tokenize(text: str, *, markdown: bool = False) -> list[str]:
    """Lowercase word-token a string.

    Args:
        text: Source text.
        markdown: When True, strip markdown scaffolding first.

    Returns:
        Lowercased word tokens. For languages without whitespace word
        boundaries (e.g. CJK) this under-segments; character-level metrics carry
        the completeness signal for those pages instead.
    """
    if markdown:
        text = strip_markdown(text)
    return [match.group(0).lower() for match in _WORD_RE.finditer(text)]


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


def substring_hit_rate(text: str, needles: list[str]) -> float | None:
    """Fraction of anchor substrings present in ``text`` (case-insensitive).

    Args:
        text: Haystack (typically the scraper markdown).
        needles: Curated anchor substrings.

    Returns:
        Fraction in ``[0, 1]``, or ``None`` when no anchors were supplied.
    """
    if not needles:
        return None
    haystack = text.lower()
    hits = sum(1 for needle in needles if needle.lower() in haystack)
    return hits / len(needles)


def substring_absent_rate(text: str, needles: list[str]) -> float | None:
    """Fraction of boilerplate substrings correctly absent (case-insensitive).

    Args:
        text: Haystack (typically the scraper markdown).
        needles: Substrings that good output should not contain.

    Returns:
        Fraction in ``[0, 1]`` (1 means none of the boilerplate leaked), or
        ``None`` when no anchors were supplied.
    """
    if not needles:
        return None
    haystack = text.lower()
    absent = sum(1 for needle in needles if needle.lower() not in haystack)
    return absent / len(needles)


def count_structure(markdown: str) -> dict[str, int]:
    """Count structural markdown elements.

    Code fences are counted in pairs (an opening and closing fence make one
    block); table rows are counted whole, then the customary header/separator
    pair is netted out so a simple table reports its body row count.

    Args:
        markdown: Markdown source.

    Returns:
        Mapping with ``headings``, ``code_blocks``, ``tables``, ``images`` and
        ``links`` counts.
    """
    fences = len(_FENCE_RE.findall(markdown))
    table_rows = len(_TABLE_ROW_RE.findall(markdown))
    return {
        "headings": len(_HEADING_LINE_RE.findall(markdown)),
        "code_blocks": fences // 2,
        "tables": max(0, table_rows - 2) if table_rows else 0,
        "images": len(_IMAGE_RE.findall(markdown)),
        "links": len(_LINK_RE.findall(markdown)),
    }


def link_density(link_count: int, word_count: int) -> float:
    """Links per 1000 words.

    A high density on a content page is a strong tell that navigation menus or
    link farms were not stripped.

    Args:
        link_count: Number of markdown links.
        word_count: Number of word tokens.

    Returns:
        Links per 1000 words; 0 when there are no words.
    """
    if word_count <= 0:
        return 0.0
    return link_count * 1000.0 / word_count


def composite_quality(
    *,
    success: bool,
    char_coverage_value: float | None,
    token_f1: float | None,
    noise: float | None,
    expect_hit: float | None,
    expect_absent_ok: float | None,
    link_density_value: float | None,
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

    if not components:
        # Nothing to score on but the scrape succeeded; give a neutral floor.
        return 50.0

    total_weight = sum(weight for weight, _ in components)
    score = sum(weight * value for weight, value in components) / total_weight
    return round(100.0 * score, 1)
