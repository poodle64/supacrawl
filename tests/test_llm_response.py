"""Tests for reading a reasoning model's answer out of its reply.

The failure these guard against is silent: a caller that reads
``content[0]`` off a ``[thinking, text]`` turn gets an empty string and no
exception, so every assertion here that expects real text is really
asserting "not silently empty".
"""

import pytest

from supacrawl.llm.response import strip_reasoning_preamble, text_from_blocks


class TestTextFromBlocks:
    """Selecting the answer block by shape rather than by index or type."""

    def test_plain_single_text_block(self) -> None:
        assert text_from_blocks([{"type": "text", "text": "hello"}]) == "hello"

    def test_thinking_block_first_does_not_swallow_the_answer(self) -> None:
        """The reasoning-model shape: the answer is not at index 0."""
        blocks = [
            {"type": "thinking", "thinking": "let me work this out", "signature": "sig"},
            {"type": "text", "text": '{"title": "Real answer"}'},
        ]

        assert text_from_blocks(blocks) == '{"title": "Real answer"}'

    def test_redacted_thinking_block_contributes_nothing(self) -> None:
        blocks = [
            {"type": "redacted_thinking", "data": "encrypted"},
            {"type": "text", "text": "answer"},
        ]

        assert text_from_blocks(blocks) == "answer"

    def test_tool_use_block_contributes_nothing(self) -> None:
        blocks = [
            {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
            {"type": "text", "text": "answer"},
        ]

        assert text_from_blocks(blocks) == "answer"

    def test_multiple_text_blocks_join_in_order(self) -> None:
        blocks = [
            {"type": "text", "text": "first "},
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": "second"},
        ]

        assert text_from_blocks(blocks) == "first second"

    def test_block_without_a_type_field_is_still_read(self) -> None:
        """Selection is by shape, so a gateway that omits `type` still works."""
        assert text_from_blocks([{"text": "answer"}]) == "answer"

    def test_object_blocks_are_accepted(self) -> None:
        """SDK responses hand back objects, not dicts."""

        class Thinking:
            thinking = "reasoning"

        class Text:
            text = "answer"

        assert text_from_blocks([Thinking(), Text()]) == "answer"

    def test_bare_string_passes_through(self) -> None:
        assert text_from_blocks("already a string") == "already a string"

    @pytest.mark.parametrize("content", [None, [], {}, 42])
    def test_no_text_available_yields_empty(self, content: object) -> None:
        assert text_from_blocks(content) == ""

    def test_non_string_text_attribute_is_ignored(self) -> None:
        assert text_from_blocks([{"text": None}, {"text": "answer"}]) == "answer"


class TestStripReasoningPreamble:
    """Removing a leading <think> preamble without eating real content."""

    def test_leading_preamble_is_removed(self) -> None:
        raw = '<think>weighing options</think>\n{"result": true}'

        assert strip_reasoning_preamble(raw) == '{"result": true}'

    def test_attributed_open_tag_is_still_a_preamble(self) -> None:
        raw = '<think reasoning="true">hmm</think>answer'

        assert strip_reasoning_preamble(raw) == "answer"

    def test_uppercase_tag_is_still_a_preamble(self) -> None:
        assert strip_reasoning_preamble("<THINK>hmm</THINK>answer") == "answer"

    def test_leading_whitespace_before_the_tag_is_tolerated(self) -> None:
        assert strip_reasoning_preamble("\n  <think>hmm</think>answer") == "answer"

    def test_nested_preamble_matches_its_own_close(self) -> None:
        """A non-greedy match would leave the outer tail and an orphan tag."""
        raw = "<think>outer <think>inner</think> more outer</think>answer"

        assert strip_reasoning_preamble(raw) == "answer"

    def test_mid_string_think_tag_is_content_and_survives(self) -> None:
        raw = "The model emits <think> tags when reasoning."

        assert strip_reasoning_preamble(raw) == raw

    def test_greedy_match_would_eat_a_quoted_close_tag(self) -> None:
        """The answer's own prose may mention </think>; it must survive."""
        raw = "<think>reasoning</think>Docs say </think> closes the block."

        assert strip_reasoning_preamble(raw) == "Docs say </think> closes the block."

    def test_unterminated_preamble_is_left_intact(self) -> None:
        """Cut off mid-reasoning: returning "" would be the silent failure."""
        raw = "<think>reasoning that never finished"

        assert strip_reasoning_preamble(raw) == raw

    def test_text_without_a_preamble_is_untouched(self) -> None:
        assert strip_reasoning_preamble('{"result": true}') == '{"result": true}'

    def test_non_string_input_passes_through(self) -> None:
        assert strip_reasoning_preamble(None) is None  # type: ignore[arg-type]
