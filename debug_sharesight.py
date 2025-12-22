#!/usr/bin/env python3
"""Debug script to test Playwright navigation to Sharesight API."""

import asyncio
from playwright.async_api import async_playwright


async def test_navigation():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible browser
        page = await browser.new_page()

        print("Navigating to https://portfolio.sharesight.com/api/3/codes")
        try:
            await page.goto("https://portfolio.sharesight.com/api/3/codes", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Navigation error: {e}")

        print("\nWaiting 5 seconds for any client-side routing...")
        await asyncio.sleep(5)

        # Check what URL we're actually at
        current_url = page.url
        print(f"\nCurrent URL: {current_url}")

        # Check page title
        title = await page.title()
        print(f"Page title: {title}")

        # Check for h1 heading
        h1 = await page.query_selector("h1")
        if h1:
            h1_text = await h1.text_content()
            print(f"H1 heading: {h1_text}")

        # Check if "Market codes" text exists
        market_codes = await page.query_selector('text="Market codes"')
        print(f"\n'Market codes' found: {market_codes is not None}")

        # Get HTML length
        html = await page.content()
        print(f"HTML length: {len(html)} characters")
        print(f"HTML lines: {len(html.splitlines())}")

        # Search for codes in HTML
        if "Market codes" in html:
            print("\n✓ 'Market codes' IS in the HTML!")
        else:
            print("\n✗ 'Market codes' is NOT in the HTML")

        if "User API V3 - Overview" in html:
            print("✗ 'Overview' content IS present (wrong page)")
        else:
            print("✓ 'Overview' content is NOT present (correct)")

        # Take screenshot for manual inspection
        await page.screenshot(path="/tmp/sharesight-codes-debug.png")
        print("\nScreenshot saved to /tmp/sharesight-codes-debug.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_navigation())
