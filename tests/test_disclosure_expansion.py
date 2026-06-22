"""Tests for the _expand_disclosures method in BrowserManager.

The expansion logic runs in-browser JS against a Playwright page. These tests
inject local fixture HTML via page.set_content() to verify:
  - Closed <details> elements are opened.
  - Collapsed aria-expanded="false" content buttons are clicked/revealed.
  - Navigation chrome (nav menus, hamburger buttons) is left untouched.
  - Pages with no collapsed disclosures are unchanged (no-op, cost ≈ zero).

Tests are marked @pytest.mark.integration because they spin up a real Playwright
browser. They do NOT hit the network; all HTML is served via set_content().
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fixture HTML
# ---------------------------------------------------------------------------

# A page with:
#   - One closed <details> + <summary>  → should be opened (open attr added)
#   - One aria-expanded="false" content button + hidden panel  → should be clicked
#   - One nav aria-expanded="false" hamburger  → should stay closed
_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Disclosure test</title></head>
<body>
  <!-- Content disclosure 1: <details> -->
  <details id="faq-details">
    <summary>FAQ item</summary>
    <p id="faq-body">Hidden FAQ content that should become visible.</p>
  </details>

  <!-- Content disclosure 2: aria-expanded button with aria-controls -->
  <button id="accordion-btn" aria-expanded="false" aria-controls="accordion-panel">
    Show more
  </button>
  <div id="accordion-panel" style="display:none">
    <p id="accordion-content">Accordion body content.</p>
  </div>
  <script>
    // Simulate the real accordion JS: clicking the button toggles the panel.
    document.getElementById('accordion-btn').addEventListener('click', function() {
      var panel = document.getElementById('accordion-panel');
      var btn = this;
      if (btn.getAttribute('aria-expanded') === 'false') {
        btn.setAttribute('aria-expanded', 'true');
        panel.style.display = 'block';
      } else {
        btn.setAttribute('aria-expanded', 'false');
        panel.style.display = 'none';
      }
    });
  </script>

  <!-- Nav chrome: hamburger menu  → must NOT be expanded -->
  <nav id="site-nav">
    <button id="hamburger" aria-expanded="false" aria-controls="nav-menu"
            class="hamburger">
      Menu
    </button>
    <ul id="nav-menu" style="display:none">
      <li>Home</li>
      <li>About</li>
    </ul>
    <script>
      document.getElementById('hamburger').addEventListener('click', function() {
        var menu = document.getElementById('nav-menu');
        var btn = this;
        if (btn.getAttribute('aria-expanded') === 'false') {
          btn.setAttribute('aria-expanded', 'true');
          menu.style.display = 'block';
        } else {
          btn.setAttribute('aria-expanded', 'false');
          menu.style.display = 'none';
        }
      });
    </script>
  </nav>
</body>
</html>"""

# A page with a bare button (aria-expanded but NO aria-controls) — must NOT be clicked.
_BARE_ACTION_BUTTON_HTML = """<!DOCTYPE html>
<html>
<head><title>Bare action button</title></head>
<body>
  <!-- A button that uses aria-expanded as a state flag (e.g. sort/filter)
       but carries no aria-controls link to a disclosure region. -->
  <button id="sort-btn" aria-expanded="false">Sort options</button>
  <div id="sort-panel" style="display:none">Ascending / Descending</div>
  <script>
    document.getElementById('sort-btn').addEventListener('click', function() {
      document.getElementById('sort-panel').style.display = 'block';
      this.setAttribute('aria-expanded', 'true');
    });
  </script>
</body>
</html>"""

# A page with only closed <details> (no JS accordion buttons).
# Expansion must happen but incur no settle wait.
_DETAILS_ONLY_HTML = """<!DOCTYPE html>
<html>
<head><title>Details only</title></head>
<body>
  <details id="d1">
    <summary>Section 1</summary>
    <p id="d1-body">Content 1</p>
  </details>
  <details id="d2">
    <summary>Section 2</summary>
    <p id="d2-body">Content 2</p>
  </details>
</body>
</html>"""

# A page with no collapsed disclosures at all.
_NO_DISCLOSURES_HTML = """<!DOCTYPE html>
<html>
<head><title>Plain page</title></head>
<body>
  <h1>No collapsibles here</h1>
  <p>Just regular content.</p>
</body>
</html>"""

# A page where all disclosures are already open (idempotency check).
_ALREADY_OPEN_HTML = """<!DOCTYPE html>
<html>
<head><title>Already open</title></head>
<body>
  <details id="open-details" open>
    <summary>Already visible</summary>
    <p id="open-body">Already showing.</p>
  </details>
  <button id="open-btn" aria-expanded="true" aria-controls="open-panel">
    Collapse
  </button>
  <div id="open-panel">Visible panel content.</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_expand(page) -> int:  # type: ignore[type-arg]
    """Call BrowserManager._expand_disclosures against an already-set page."""
    from supacrawl.services.browser import BrowserManager

    # Instantiate without starting the browser — we call the method directly on
    # an externally-created page so we don't need a full BrowserManager context.
    mgr = BrowserManager.__new__(BrowserManager)
    return await mgr._expand_disclosures(page)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_details_element_is_opened() -> None:
    """Closed <details> elements receive the open attribute."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(_FIXTURE_HTML)

        count = await _run_expand(page)

        # The <details> must now carry the open attribute.
        open_attr = await page.get_attribute("#faq-details", "open")
        assert open_attr is not None, "<details> should have been opened (open attr set)"
        assert count >= 1, f"Expected at least 1 disclosure expanded, got {count}"

        await browser.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accordion_button_is_clicked() -> None:
    """aria-expanded='false' content button is clicked and its panel is revealed."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(_FIXTURE_HTML)

        count = await _run_expand(page)

        # The button's aria-expanded must now be 'true'.
        expanded = await page.get_attribute("#accordion-btn", "aria-expanded")
        assert expanded == "true", f"Accordion button should have aria-expanded='true' after expand, got {expanded!r}"
        # The panel must be visible (display changed from 'none').
        display = await page.evaluate("document.getElementById('accordion-panel').style.display")
        assert display != "none", f"Accordion panel should be visible, got display={display!r}"
        assert count >= 1

        await browser.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nav_hamburger_is_not_clicked() -> None:
    """Nav-chrome aria-expanded='false' hamburger is excluded from expansion."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(_FIXTURE_HTML)

        await _run_expand(page)

        # The hamburger must still be aria-expanded='false'.
        expanded = await page.get_attribute("#hamburger", "aria-expanded")
        assert expanded == "false", f"Nav hamburger should remain collapsed, got aria-expanded={expanded!r}"
        # The nav menu must still be hidden.
        display = await page.evaluate("document.getElementById('nav-menu').style.display")
        assert display == "none", f"Nav menu should remain hidden, got display={display!r}"

        await browser.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_op_on_page_without_disclosures() -> None:
    """A page with no collapsed disclosures is captured byte-identically (count==0)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(_NO_DISCLOSURES_HTML)

        html_before = await page.content()
        count = await _run_expand(page)
        html_after = await page.content()

        assert count == 0, f"Expected 0 disclosures expanded on plain page, got {count}"
        assert html_before == html_after, "HTML should be unchanged on a page with no disclosures"

        await browser.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_on_already_open_disclosures() -> None:
    """Already-open disclosures are not re-toggled (idempotency guard)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(_ALREADY_OPEN_HTML)

        count = await _run_expand(page)

        # The already-open <details> must still be open.
        open_attr = await page.get_attribute("#open-details", "open")
        assert open_attr is not None, "<details> that was already open should remain open"

        # The already-open button must still be aria-expanded='true'.
        expanded = await page.get_attribute("#open-btn", "aria-expanded")
        assert expanded == "true", f"Already-open button should stay aria-expanded='true', got {expanded!r}"

        # Count must be 0 — nothing was collapsed to begin with.
        assert count == 0, f"Expected 0 disclosures expanded (all already open), got {count}"

        await browser.close()


@pytest.mark.unit
def test_expand_disclosures_param_exists() -> None:
    """BrowserManager.fetch_page accepts expand_disclosures keyword."""
    import inspect

    from supacrawl.services.browser import BrowserManager

    sig = inspect.signature(BrowserManager.fetch_page)
    assert "expand_disclosures" in sig.parameters, "fetch_page must have an expand_disclosures parameter"
    param = sig.parameters["expand_disclosures"]
    assert param.default is True, f"expand_disclosures default must be True (always-on), got {param.default!r}"


@pytest.mark.unit
def test_scrape_service_expand_disclosures_param_exists() -> None:
    """ScrapeService.scrape accepts expand_disclosures keyword with default True."""
    import inspect

    from supacrawl.services.scrape import ScrapeService

    sig = inspect.signature(ScrapeService.scrape)
    assert "expand_disclosures" in sig.parameters, "ScrapeService.scrape must have an expand_disclosures parameter"
    param = sig.parameters["expand_disclosures"]
    assert param.default is True, f"expand_disclosures default must be True, got {param.default!r}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bare_action_button_not_clicked() -> None:
    """A button with aria-expanded='false' but NO aria-controls is NOT clicked.

    Action buttons (sort, filter, load-more) use aria-expanded as a state flag
    but do not link to a disclosure region via aria-controls. The hardened
    predicate must leave these untouched.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(_BARE_ACTION_BUTTON_HTML)

        count = await _run_expand(page)

        # The sort button must remain collapsed — no aria-controls, so not a disclosure.
        expanded = await page.get_attribute("#sort-btn", "aria-expanded")
        assert expanded == "false", (
            f"Bare action button (no aria-controls) must not be clicked; aria-expanded is now {expanded!r}"
        )
        display = await page.evaluate("document.getElementById('sort-panel').style.display")
        assert display == "none", f"Sort panel should still be hidden, got display={display!r}"
        # No expansion should have been counted.
        assert count == 0, f"Expected 0 expansions on bare action-button page, got {count}"

        await browser.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_details_only_no_settle_wait() -> None:
    """A page with only closed <details> is expanded but incurs no settle wait.

    <details> are opened synchronously via setAttribute('open'). The 1.2 s settle
    wait must fire only when at least one JS click() was issued. Verify by
    measuring wall-clock time: the call must complete well under the 1.2 s
    threshold.
    """
    try:
        import time

        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(_DETAILS_ONLY_HTML)

        t0 = time.monotonic()
        count = await _run_expand(page)
        elapsed = time.monotonic() - t0

        # Both <details> must have been opened.
        assert count == 2, f"Expected 2 details opened, got {count}"
        open1 = await page.get_attribute("#d1", "open")
        open2 = await page.get_attribute("#d2", "open")
        assert open1 is not None, "<details id=d1> should be open"
        assert open2 is not None, "<details id=d2> should be open"

        # No JS click was issued, so we must NOT have paid the 1.2 s settle wait.
        # Allow generous headroom (300 ms) for browser startup variance.
        assert elapsed < 0.8, (
            f"Expected <details>-only expand to complete in <0.8 s (no settle wait), "
            f"but it took {elapsed:.3f} s — the settle wait may have fired incorrectly"
        )

        await browser.close()
