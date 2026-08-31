"""Tests for routing disclosure-gated pages into the browser (#142).

The failure is silent by construction: a page that hides content behind a
collapsed accordion still returns perfectly good text for the part it *did*
render, so it scores "ok" on the HTTP-first path and no quality signal ever
fires. Only the browser runs `_expand_disclosures`, so the gated content is
dropped with no error.

The other half of the bargain matters just as much: escalating a page that
has nothing to expand would trade supacrawl's fast default for nothing, so
the negative cases below are load-bearing, not padding.
"""

import pytest

from supacrawl.services.detection import detect_collapsed_disclosures

# A page server-rendered enough to satisfy the fast path, with real prose so it
# cannot be mistaken for a JS shell by the sibling heuristic.
_PROSE = "Council rates are calculated per the schedule below. " * 20


def _page(body: str) -> str:
    return f"<html><body><h1>Rates</h1><p>{_PROSE}</p>{body}</body></html>"


class TestGatedPagesAreDetected:
    """Cases that must escalate: the browser would reveal more."""

    def test_closed_details_is_gated(self) -> None:
        html = _page("<details><summary>Fee schedule</summary><p>Band A: $412</p></details>")

        assert detect_collapsed_disclosures(html) is True

    def test_collapsed_aria_accordion_is_gated(self) -> None:
        html = _page(
            '<button aria-expanded="false" aria-controls="panel1">Fee schedule</button>'
            '<div id="panel1" hidden><p>Band A: $412</p></div>'
        )

        assert detect_collapsed_disclosures(html) is True

    def test_one_closed_among_open_details_is_enough(self) -> None:
        html = _page(
            "<details open><summary>Open</summary><p>visible</p></details>"
            "<details><summary>Closed</summary><p>hidden</p></details>"
        )

        assert detect_collapsed_disclosures(html) is True

    def test_multi_valued_class_attribute_does_not_crash(self) -> None:
        """BeautifulSoup hands `class` back as a list, not a string."""
        html = _page('<details class="accordion panel wide"><summary>s</summary><p>x</p></details>')

        assert detect_collapsed_disclosures(html) is True


class TestFastPathIsPreserved:
    """Cases that must NOT escalate: the browser would reveal nothing."""

    def test_ordinary_page_is_not_gated(self) -> None:
        assert detect_collapsed_disclosures(_page("<p>Nothing collapsed here.</p>")) is False

    def test_already_open_details_is_not_gated(self) -> None:
        html = _page("<details open><summary>Fee schedule</summary><p>Band A: $412</p></details>")

        assert detect_collapsed_disclosures(html) is False

    def test_hamburger_menu_is_not_gated(self) -> None:
        """The commonest false positive: every mobile site has one of these."""
        html = _page(
            '<nav><button aria-expanded="false" aria-controls="menu">Menu</button>'
            '<ul id="menu"><li>Home</li></ul></nav>'
        )

        assert detect_collapsed_disclosures(html) is False

    def test_nav_by_role_is_not_gated(self) -> None:
        html = _page('<div role="navigation"><button aria-expanded="false" aria-controls="m">Menu</button></div>')

        assert detect_collapsed_disclosures(html) is False

    def test_nav_by_class_is_not_gated(self) -> None:
        html = _page('<div class="site-nav"><button aria-expanded="false" aria-controls="m">Menu</button></div>')

        assert detect_collapsed_disclosures(html) is False

    def test_details_inside_nav_is_not_gated(self) -> None:
        html = _page("<nav><details><summary>More</summary><a href='/x'>X</a></details></nav>")

        assert detect_collapsed_disclosures(html) is False

    def test_action_button_without_aria_controls_is_not_gated(self) -> None:
        """A sort/filter button uses aria-expanded as a bare state flag."""
        html = _page('<button aria-expanded="false">Sort</button>')

        assert detect_collapsed_disclosures(html) is False

    def test_submit_button_is_not_gated(self) -> None:
        html = _page('<button type="submit" aria-expanded="false" aria-controls="f">Go</button>')

        assert detect_collapsed_disclosures(html) is False

    def test_summary_inside_open_details_is_not_double_counted(self) -> None:
        html = _page(
            "<details open>"
            '<summary aria-expanded="false" aria-controls="c">Fee schedule</summary>'
            '<p id="c">Band A: $412</p></details>'
        )

        assert detect_collapsed_disclosures(html) is False

    @pytest.mark.parametrize("html", ["", "<html><body></body></html>", "not html at all"])
    def test_degenerate_input_is_not_gated(self, html: str) -> None:
        assert detect_collapsed_disclosures(html) is False


class TestAgreementWithTheExpander:
    """The detector must not claim a page the browser would leave alone.

    `BrowserManager._expand_disclosures` is the authority on what gets opened;
    this predicate only decides whether running it is worth a browser. If they
    disagree, the escalation is pure cost.
    """

    def test_selectors_match_the_browser_side(self) -> None:
        import inspect

        from supacrawl.services.browser import BrowserManager

        source = inspect.getsource(BrowserManager._expand_disclosures)

        assert "details:not([open])" in source
        assert '[aria-expanded="false"]' in source
        assert "aria-controls" in source
