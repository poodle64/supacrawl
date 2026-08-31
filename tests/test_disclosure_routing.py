"""Tests for routing disclosure-gated pages into the browser (#142).

The failure is silent by construction: a page that hides content behind a
collapsed accordion still returns perfectly good text for the part it *did*
render, so it scores "ok" on the HTTP-first path and no quality signal ever
fires. Only the browser runs `_expand_disclosures`, so the gated content is
dropped with no error.

The question the predicate must answer is NOT "is anything collapsed?" but
"would the fast path's own output miss it?" — those diverge, and getting it
wrong in the permissive direction costs a browser render on a large fraction
of the web. Measured against the real `MarkdownConverter`: a closed <details>
and a Bootstrap `.collapse` panel both have their text emitted into the fast
path's markdown already, so neither is gated. What genuinely goes missing is a
panel hidden by `[hidden]` / `.hidden` / inline `display:none`, or one the site
injects on first click so it is not in the DOM at all.

The negative cases below are therefore load-bearing, not padding.
"""

import pytest

from supacrawl.services.converter import MarkdownConverter
from supacrawl.services.detection import detect_collapsed_disclosures

# A page server-rendered enough to satisfy the fast path, with real prose so it
# cannot be mistaken for a JS shell by the sibling heuristic.
_PROSE = "Council rates are calculated per the schedule below. " * 20


def _page(body: str) -> str:
    return f"<html><body><main><h1>Rates</h1><p>{_PROSE}</p>{body}</main></body></html>"


def _control(target: str = "panel1", label: str = "Fee schedule") -> str:
    return f'<button aria-expanded="false" aria-controls="{target}">{label}</button>'


class TestContentTheFastPathWouldMiss:
    """Cases that must escalate: the browser would reveal more."""

    def test_panel_injected_on_click_is_gated(self) -> None:
        """`aria-controls` names an id nothing matches — the panel is not here yet."""
        html = _page(_control())

        assert detect_collapsed_disclosures(html) is True

    def test_hidden_attribute_panel_is_gated(self) -> None:
        html = _page(_control() + '<div id="panel1" hidden><p>Band A: $412 per quarter.</p></div>')

        assert detect_collapsed_disclosures(html) is True

    def test_display_none_panel_is_gated(self) -> None:
        html = _page(_control() + '<div id="panel1" style="display: none"><p>Band A: $412.</p></div>')

        assert detect_collapsed_disclosures(html) is True

    def test_hidden_class_panel_is_gated(self) -> None:
        html = _page(_control() + '<div id="panel1" class="hidden"><p>Band A: $412.</p></div>')

        assert detect_collapsed_disclosures(html) is True

    def test_hidden_ancestor_counts(self) -> None:
        """The panel itself may be plain; what matters is whether it is reachable."""
        html = _page(_control() + '<div hidden><div id="panel1"><p>Band A: $412.</p></div></div>')

        assert detect_collapsed_disclosures(html) is True

    def test_single_quoted_attributes_are_detected(self) -> None:
        """Valid HTML. A value-specific substring pre-check silently missed these."""
        html = _page("<button aria-expanded='false' aria-controls='panel1'>Fees</button>")

        assert detect_collapsed_disclosures(html) is True

    def test_whitespace_around_equals_is_detected(self) -> None:
        html = _page('<button aria-expanded = "false" aria-controls="panel1">Fees</button>')

        assert detect_collapsed_disclosures(html) is True

    def test_hidden_prose_citing_sources_is_still_gated(self) -> None:
        """The link-list exclusion must not swallow real content that cites sources."""
        html = _page(
            _control() + '<div id="panel1" hidden><p>Band A is charged at $412 per quarter, reviewed '
            "each June under the rating strategy, with concessions applied automatically "
            'to eligible ratepayers. See <a href="/a">the schedule</a>, '
            '<a href="/b">concessions</a> and <a href="/c">appeals</a>.</p></div>'
        )

        assert detect_collapsed_disclosures(html) is True


class TestFastPathIsPreserved:
    """Cases that must NOT escalate: the fast path already has the content."""

    def test_ordinary_page_is_not_gated(self) -> None:
        assert detect_collapsed_disclosures(_page("<p>Nothing collapsed here.</p>")) is False

    def test_closed_details_is_not_gated(self) -> None:
        """The converter emits a closed <details>'s text, so nothing is missing."""
        html = _page("<details><summary>Fee schedule</summary><p>Band A: $412.</p></details>")

        assert detect_collapsed_disclosures(html) is False

    def test_bootstrap_collapse_panel_is_not_gated(self) -> None:
        """Bootstrap hides via its own stylesheet, which the converter cannot see.

        The text is in the fast path's markdown already. Escalating for this
        would drag every Bootstrap accordion, FAQ and filter panel on the web
        onto the slow path for no content gained.
        """
        html = _page(_control() + '<div id="panel1" class="accordion-collapse collapse"><p>Band A: $412.</p></div>')

        assert detect_collapsed_disclosures(html) is False

    def test_visible_panel_is_not_gated(self) -> None:
        html = _page(_control() + '<div id="panel1"><p>Band A: $412.</p></div>')

        assert detect_collapsed_disclosures(html) is False

    def test_hamburger_menu_is_not_gated(self) -> None:
        """The commonest false positive: every mobile site has one of these."""
        html = _page(
            '<nav><button aria-expanded="false" aria-controls="menu">Menu</button>'
            '<ul id="menu" hidden><li>Home</li></ul></nav>'
        )

        assert detect_collapsed_disclosures(html) is False

    def test_nav_by_role_is_not_gated(self) -> None:
        html = _page(f'<div role="navigation">{_control("m", "Menu")}</div><div id="m" hidden>x</div>')

        assert detect_collapsed_disclosures(html) is False

    def test_nav_by_class_is_not_gated(self) -> None:
        html = _page(f'<div class="site-nav">{_control("m", "Menu")}</div><div id="m" hidden>x</div>')

        assert detect_collapsed_disclosures(html) is False

    def test_hidden_link_list_is_not_gated(self) -> None:
        """A hidden menu is still a menu, whatever its markup says."""
        links = "".join(f'<a href="/s{i}">Section {i}</a>' for i in range(12))
        html = _page(_control("panel1", "More") + f'<div id="panel1" hidden>{links}</div>')

        assert detect_collapsed_disclosures(html) is False

    def test_action_button_without_aria_controls_is_not_gated(self) -> None:
        """A sort/filter button uses aria-expanded as a bare state flag."""
        html = _page('<button aria-expanded="false">Sort</button>')

        assert detect_collapsed_disclosures(html) is False

    def test_submit_button_is_not_gated(self) -> None:
        html = _page('<button type="submit" aria-expanded="false" aria-controls="f">Go</button>')

        assert detect_collapsed_disclosures(html) is False

    def test_combobox_input_is_not_gated(self) -> None:
        """Real case: GitHub's file-search box is an ARIA combobox, not a disclosure.

        The expander clicks it and reveals nothing — suggestions appear on
        typing — so escalating for one is pure cost.
        """
        html = _page('<input aria-expanded="false" aria-controls="file-results-list">')

        assert detect_collapsed_disclosures(html) is False

    def test_select_and_textarea_are_not_gated(self) -> None:
        html = _page(
            '<select aria-expanded="false" aria-controls="opts"><option>a</option></select>'
            '<textarea aria-expanded="false" aria-controls="hint"></textarea>'
        )

        assert detect_collapsed_disclosures(html) is False

    def test_expanded_control_is_not_gated(self) -> None:
        html = _page('<button aria-expanded="true" aria-controls="panel1">Fees</button>')

        assert detect_collapsed_disclosures(html) is False

    @pytest.mark.parametrize("html", ["", "<html><body></body></html>", "not html at all"])
    def test_degenerate_input_is_not_gated(self, html: str) -> None:
        assert detect_collapsed_disclosures(html) is False


class TestAgreementWithTheConverter:
    """The predicate's premise, asserted against the real converter.

    These are the measurements the whole design rests on. If the converter's
    boilerplate handling changes, the predicate's idea of "gated" goes stale
    silently — so it is checked here rather than assumed.
    """

    @staticmethod
    def _markdown(html: str) -> str:
        return MarkdownConverter().convert(html, base_url="https://x.example", only_main_content=True)

    @pytest.mark.parametrize(
        "body",
        [
            # A closed <details> needs no separate control — <summary> is its own.
            "<details><summary>S</summary><p>NEEDLE</p></details>",
            _control() + '<div id="panel1" class="accordion-collapse collapse"><p>NEEDLE</p></div>',
            _control() + '<div id="panel1"><p>NEEDLE</p></div>',
        ],
    )
    def test_converter_already_emits_these(self, body: str) -> None:
        """So escalating for them would buy nothing."""
        html = _page(body)

        assert "NEEDLE" in self._markdown(html)
        assert detect_collapsed_disclosures(html) is False

    @pytest.mark.parametrize(
        "body",
        [
            '<div id="panel1" hidden><p>NEEDLE</p></div>',
            '<div id="panel1" style="display:none"><p>NEEDLE</p></div>',
            '<div id="panel1" class="hidden"><p>NEEDLE</p></div>',
            "",  # injected on click — not in the DOM at all
        ],
    )
    def test_converter_drops_these_so_the_browser_is_worth_it(self, body: str) -> None:
        html = _page(_control() + body)

        assert "NEEDLE" not in self._markdown(html)
        assert detect_collapsed_disclosures(html) is True
