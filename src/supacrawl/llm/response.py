"""Reading a model's actual answer out of a reasoning model's reply.

A reasoning model does not put its answer where a plain model put it, and
both provider surfaces supacrawl speaks moved under it on the same day
(29/08/2026, when the household's deep model became a reasoning model).

On the **Anthropic-shape** surface (``/v1/messages``) the assistant turn
arrives as ``[thinking, text]`` rather than ``[text]``. A caller that
reaches for ``content[0]`` lands on the thinking block, which carries no
``text`` at all.

On the **OpenAI chat-completions** surface the same reply arrives as a
single string with a leading ``<think>…</think>`` preamble. A caller that
``json.loads`` the whole string raises on the preamble — which is how
:meth:`LLMClient.chat_json` and every ``llm-extract`` run would fail.

Both helpers exist so there is ONE answer to "what did the model actually
say", and a block type or a preamble appearing in front of the text can
never quietly break a caller again.

Which layer introduces the mess matters when reproducing it: verified live
on 01/09/2026 against the real reasoning model, Ollama's own APIs are clean
on both surfaces — the native one puts reasoning in ``message.thinking`` and
its OpenAI-compatible one in ``message.reasoning``, leaving ``content``
parseable. The ``[thinking, text]`` blocks and the ``<think>`` preamble come
from a gateway re-serialising in front of it, so pointing straight at Ollama
will not reproduce either.

This mirrors ``mcp_common.model_response`` in the household's mcp-servers
monorepo, deliberately copied rather than imported: supacrawl is a public
package and cannot take a private dependency (the same constraint already
recorded for this repo's publish workflow). Keep the two aligned.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["strip_reasoning_preamble", "text_from_blocks"]


def _block_text(block: Any) -> str | None:
    """Return a block's ``text`` when it carries one, else None.

    Selection is by SHAPE, not by a ``type`` field. In the Anthropic
    content-block set a text block is exactly the block carrying a string
    ``text``: ``thinking`` carries ``thinking``, ``redacted_thinking``
    carries ``data``, and ``tool_use`` carries ``input`` — none of them
    has a ``text`` to contribute. Shape also keeps this working against
    gateway block objects, which do not always populate ``type``.

    Blocks arrive as dicts when the response was parsed from JSON and as
    objects when it came from an SDK, so both are accepted.
    """
    text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
    return text if isinstance(text, str) else None


def text_from_blocks(content: Any) -> str:
    """Return the concatenated text of every text block in ``content``.

    Args:
        content: An Anthropic-shape content list (or a bare string, which
            is returned unchanged — some providers still send one).

    Returns:
        The assistant's text, blocks joined in order. ``""`` when there is
        no content or it carries no text block at all.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(text for block in content if (text := _block_text(block)) is not None)


# Anchored at the start: a reasoning preamble is by definition what comes
# BEFORE the answer. An unanchored search would happily cut a <think> that
# the model was quoting, or one inside the answer's own prose, and silently
# discard real content.
#
# `<think\b[^>]*>` rather than `<think>` because an attributed variant
# (`<think reasoning="true">`) is still a preamble, and a literal match would
# leave it in place — the silent no-op that looks exactly like a clean answer.
_OPEN_THINK = re.compile(r"\A\s*<think\b[^>]*>", re.IGNORECASE)
_ANY_THINK_TAG = re.compile(r"<(/?)think\b[^>]*>", re.IGNORECASE)


def strip_reasoning_preamble(text: str) -> str:
    """Strip a LEADING ``<think>…</think>`` preamble from ``text``.

    Only a preamble is removed — a ``<think>`` appearing mid-string is
    left alone, because there it is content the model meant to send, not
    reasoning wrapped around the answer.

    Nesting is counted rather than assumed away. A non-greedy ``.*?`` would
    stop at the FIRST ``</think>``, so a nested preamble would leave the
    outer reasoning's tail and an orphaned closing tag glued to the front of
    the answer — which then fails to parse, reproducing the very failure this
    module exists to prevent. A greedy match is no better: it would run past
    a legitimate ``</think>`` in the answer's own prose and eat real content.
    Only matching the open tag to its own close is correct in both cases.

    An unterminated ``<think>`` (the model was cut off mid-reasoning, so
    there is no answer after it) is left untouched: there is nothing to
    return but reasoning, and silently yielding ``""`` would reproduce
    exactly the empty-string failure this module exists to prevent.

    Args:
        text: Raw assistant content from a chat-completions response.

    Returns:
        ``text`` with any leading reasoning preamble removed.
    """
    if not isinstance(text, str):
        return text

    opening = _OPEN_THINK.match(text)
    if opening is None:
        return text

    depth = 1
    for tag in _ANY_THINK_TAG.finditer(text, opening.end()):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return text[tag.end() :].lstrip()
    # Unterminated: hand back everything rather than invent an empty answer.
    return text
