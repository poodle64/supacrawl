"""Scrape service for single URL content extraction.

Anti-Bot Features (automatic, no configuration needed):
    - Basic fingerprint evasion: navigator.webdriver=false, chrome runtime objects,
      plugins array, languages array, WebGL vendor spoofing, canvas noise
    - Standard browser headers: Accept-Language, Sec-Fetch-*, etc.
    - Automatic bot detection: Detects 403/429/503, CAPTCHA pages, Cloudflare challenges

Enhanced Stealth (optional, for heavily protected sites):
    - Install: pip install supacrawl[stealth]
    - Auto-retry: If bot detection is suspected, automatically retries with Patchright
    - Force stealth: Use stealth=True or --stealth flag

CAPTCHA Solving (optional, requires third-party service):
    - Install: pip install supacrawl[captcha]
    - Configure: export CAPTCHA_API_KEY=your-2captcha-api-key
    - Usage: Use solve_captcha=True or --solve-captcha flag
    - Supports: reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile
    - COST WARNING: ~$2-3 per 1000 solves
"""

import base64
import logging
import re
from pathlib import Path
from typing import Any, Literal

from bs4 import BeautifulSoup

from supacrawl.cache import CacheManager
from supacrawl.exceptions import ProviderError
from supacrawl.models import ActionsOutput, ScrapeActionResult, ScrapeData, ScrapeMetadata, ScrapeResult
from supacrawl.services.browser import BrowserManager
from supacrawl.services.converter import MarkdownConverter

LOGGER = logging.getLogger(__name__)

# Type alias for wait_until options
type WaitUntilType = Literal["commit", "domcontentloaded", "load", "networkidle"]

# Patterns that indicate bot detection or blocking
BOT_DETECTION_PATTERNS = [
    r"captcha",
    r"challenge",
    r"cloudflare",
    r"ddos.protection",
    r"access.denied",
    r"blocked",
    r"robot",
    r"bot.detection",
    r"verify.you.are.human",
    r"please.wait",
    r"checking.your.browser",
    r"just.a.moment",
    r"enable.javascript",
    r"ray.id",  # Cloudflare Ray ID
]
BOT_DETECTION_REGEX = re.compile("|".join(BOT_DETECTION_PATTERNS), re.IGNORECASE)


def _is_patchright_available() -> bool:
    """Check if patchright is installed for stealth mode."""
    try:
        import patchright  # noqa: F401

        return True
    except ImportError:
        return False


def _looks_like_bot_block(status_code: int, html: str, markdown: str | None) -> bool:
    """Detect if a response looks like bot detection or blocking.

    Args:
        status_code: HTTP status code
        html: Raw HTML content
        markdown: Converted markdown content

    Returns:
        True if bot detection is suspected
    """
    # Check status codes that indicate blocking
    if status_code in (403, 429, 503):
        LOGGER.debug(f"Bot detection suspected: HTTP {status_code}")
        return True

    # Check for very short content (likely a challenge page)
    content_length = len(html) if html else 0
    if content_length < 500:
        # Very short page - might be a redirect or challenge
        if BOT_DETECTION_REGEX.search(html):
            LOGGER.debug("Bot detection suspected: short page with blocking patterns")
            return True

    # Check for bot detection patterns in HTML
    if BOT_DETECTION_REGEX.search(html):
        # Also check if content is suspiciously short for a real page
        word_count = len(markdown.split()) if markdown else 0
        if word_count < 50:
            LOGGER.debug("Bot detection suspected: blocking patterns with low word count")
            return True

    return False


def _stealth_hint() -> str:
    """Return a hint about stealth mode based on availability.

    Returns a structured hint for both humans and LLM consumers.
    Basic stealth (fingerprint evasion) is always active.
    This hint is for enhanced stealth via Patchright.
    """
    if _is_patchright_available():
        return (
            " [HINT: Basic anti-bot evasion is already active. "
            "For enhanced stealth, use --stealth flag or stealth=True]"
        )
    else:
        return (
            " [HINT: Basic anti-bot evasion is active but site may need enhanced stealth. "
            "Install with: pip install supacrawl[stealth] then retry with --stealth]"
        )


def _is_captcha_available() -> bool:
    """Check if 2captcha-python is installed for CAPTCHA solving."""
    try:
        import twocaptcha  # noqa: F401

        return True
    except ImportError:
        return False


def _captcha_hint() -> str:
    """Return a hint about CAPTCHA solving based on availability.

    Returns a structured hint for both humans and LLM consumers.
    """
    if _is_captcha_available():
        import os

        if os.environ.get("CAPTCHA_API_KEY"):
            return (
                " [HINT: CAPTCHA detected. Use --solve-captcha flag to auto-solve. "
                "WARNING: Each solve costs ~$0.002-0.003]"
            )
        else:
            return (
                " [HINT: CAPTCHA detected. CAPTCHA solving is installed but not configured. "
                "Set CAPTCHA_API_KEY environment variable, then use --solve-captcha]"
            )
    else:
        return (
            " [HINT: CAPTCHA detected. To auto-solve CAPTCHAs: "
            "1) pip install supacrawl[captcha]"
            "2) export CAPTCHA_API_KEY=your-2captcha-api-key "
            "3) use --solve-captcha flag. WARNING: Each solve costs ~$0.002-0.003]"
        )


class ScrapeService:
    """Scrape a single URL and extract content.

    IMPORTANT FOR LLM/AGENT USERS:
        This service has built-in anti-bot protection that works automatically.
        You do NOT need to configure anything for basic scraping.

    What Works Automatically (no configuration):
        - Fingerprint evasion (webdriver, plugins, WebGL, canvas)
        - Standard browser headers (Accept-Language, Sec-Fetch-*, etc.)
        - Bot detection (403/429/503, CAPTCHA, Cloudflare challenges)
        - Auto-retry with enhanced stealth if patchright is installed

    When You Might Need Enhanced Stealth:
        - Error message contains "[HINT:" with stealth suggestion
        - Getting empty content from sites that should have content
        - Seeing "Access Denied", "Please verify you are human", etc.
        - Solution: Install supacrawl[stealth] and use stealth=True

    When You Might Need CAPTCHA Solving:
        - Error message contains "[HINT: CAPTCHA detected"
        - Site requires human verification that cannot be bypassed
        - Solution: Install supacrawl[captcha], set CAPTCHA_API_KEY, use solve_captcha=True
        - WARNING: CAPTCHA solving costs money (~$0.002-0.003 per solve)

    Usage:
        # Basic scraping - anti-bot evasion is automatic
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        print(result.data.markdown)

        # With caching (recommended for repeated requests)
        service = ScrapeService(cache_dir=Path("~/.supacrawl/cache"))
        result = await service.scrape("https://example.com", max_age=3600)

        # Force enhanced stealth (for heavily protected sites)
        # Requires: pip install supacrawl[stealth]
        service = ScrapeService(stealth=True)
        result = await service.scrape("https://protected-site.com")

        # With CAPTCHA solving (for sites with mandatory verification)
        # Requires: pip install supacrawl[captcha] and CAPTCHA_API_KEY env var
        service = ScrapeService(stealth=True, solve_captcha=True)
        result = await service.scrape("https://captcha-protected-site.com")

    Returns:
        ScrapeResult with success=True/False, data (ScrapeData), and error message.
        Check result.success before accessing result.data.
    """

    def __init__(
        self,
        browser: BrowserManager | None = None,
        converter: MarkdownConverter | None = None,
        locale_config: Any | None = None,  # LocaleConfig, avoid circular import
        cache_dir: Path | None = None,
        stealth: bool = False,
        proxy: str | None = None,
        solve_captcha: bool = False,
    ):
        """Initialize scrape service.

        Args:
            browser: Optional BrowserManager (created if not provided)
            converter: Optional MarkdownConverter (created if not provided)
            locale_config: Optional LocaleConfig for browser locale/timezone settings
            cache_dir: Optional cache directory (enables caching if provided)
            stealth: Enable stealth mode via Patchright for anti-bot evasion
            proxy: Proxy URL (e.g., http://user:pass@host:port, socks5://host:port)
            solve_captcha: Enable CAPTCHA solving via 2Captcha (requires pip install supacrawl[captcha]
                          and CAPTCHA_API_KEY environment variable). WARNING: Each solve costs ~$0.002-0.003.
        """
        self._browser = browser
        self._converter = converter or MarkdownConverter()
        self._owns_browser = browser is None
        self._locale_config = locale_config
        self._stealth = stealth
        self._proxy = proxy
        self._solve_captcha = solve_captcha
        self._cache = CacheManager(cache_dir) if cache_dir else None
        self._captcha_solver: Any = None  # Lazy-loaded CaptchaSolver

    async def scrape(
        self,
        url: str,
        formats: list[
            Literal[
                "markdown", "html", "rawHtml", "links", "screenshot", "pdf", "json", "images", "branding", "summary"
            ]
        ]
        | None = None,
        only_main_content: bool = True,
        wait_for: int = 0,
        timeout: int = 30000,
        screenshot_full_page: bool = True,
        actions: list[Any] | None = None,
        json_schema: dict[str, Any] | None = None,
        json_prompt: str | None = None,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        max_age: int = 0,
        wait_until: WaitUntilType | None = None,
    ) -> ScrapeResult:
        """Scrape a URL and return content.

        Args:
            url: URL to scrape
            formats: Content formats to return (default: ["markdown"])
                     Supports: markdown, html, rawHtml, links, screenshot, pdf, json, images, branding, summary
            only_main_content: Extract main content area only
            wait_for: Additional wait time in ms after page load
            timeout: Page load timeout in ms
            screenshot_full_page: Capture full scrollable page for screenshots
            actions: List of Action objects to execute before capturing content
                     Supports: wait, click, type, scroll, screenshot, press, executeJavascript
            json_schema: JSON schema for structured extraction (for json format)
            json_prompt: Custom prompt for extraction (for json format)
            include_tags: CSS selectors for elements to include.
                         When specified, takes precedence over only_main_content.
            exclude_tags: CSS selectors for elements to exclude.
                         Applied before include_tags filtering.
            max_age: Cache freshness in seconds. 0 = no cache.
                    Returns cached content if available and fresh.
            wait_until: Page load strategy. Options: commit, domcontentloaded (default),
                       load, networkidle. Falls back to SUPACRAWL_WAIT_UNTIL env var if None.

        Returns:
            ScrapeResult with scraped content
        """
        formats = formats or ["markdown"]

        # Check cache if max_age > 0 and cache is configured
        if max_age > 0 and self._cache:
            cached = self._cache.get(url, max_age)
            if cached:
                LOGGER.debug(f"Cache hit for {url}")
                result = ScrapeResult.model_validate(cached)
                # Mark as cache hit
                if result.data and result.data.metadata:
                    result.data.metadata.cache_hit = True
                return result

        try:
            # Create browser if needed
            browser = self._browser
            owns_browser = self._owns_browser

            if owns_browser:
                browser = BrowserManager(
                    timeout_ms=timeout,
                    locale_config=self._locale_config,
                    stealth=self._stealth,
                    proxy=self._proxy,
                )
                await browser.__aenter__()

            # At this point browser is guaranteed to be set
            if browser is None:
                raise RuntimeError("Browser not initialized")

            try:
                # Determine if we need screenshot or PDF capture
                capture_screenshot = "screenshot" in formats
                capture_pdf = "pdf" in formats

                # Fetch page with actions
                page_content = await browser.fetch_page(
                    url,
                    wait_for_spa=True,
                    spa_timeout_ms=wait_for if wait_for > 0 else 5000,
                    capture_screenshot=capture_screenshot,
                    capture_pdf=capture_pdf,
                    screenshot_full_page=screenshot_full_page,
                    actions=actions,
                    wait_until=wait_until,
                )

                # Extract metadata
                metadata = await browser.extract_metadata(page_content.html)

                # Build response based on requested formats
                markdown = None
                html = None
                raw_html = None
                links = None
                images = None
                branding = None
                summary = None
                screenshot_b64 = None
                pdf_b64 = None
                json_data = None

                if "markdown" in formats or "json" in formats or "summary" in formats:
                    # Always need markdown for JSON extraction and summary generation
                    markdown = self._converter.convert(
                        page_content.html,
                        base_url=url,
                        only_main_content=only_main_content,
                        include_tags=include_tags,
                        exclude_tags=exclude_tags,
                    )

                # Check for bot detection and auto-retry with stealth if available
                if not self._stealth and _looks_like_bot_block(page_content.status_code, page_content.html, markdown):
                    if _is_patchright_available():
                        LOGGER.info(f"Bot detection suspected for {url}, retrying with stealth mode")
                        # Close current browser and retry with stealth
                        if owns_browser and browser:
                            await browser.__aexit__(None, None, None)

                        # Create stealth service and retry
                        stealth_service = ScrapeService(
                            converter=self._converter,
                            locale_config=self._locale_config,
                            cache_dir=self._cache.cache_dir if self._cache else None,
                            stealth=True,
                            proxy=self._proxy,
                            solve_captcha=self._solve_captcha,
                        )
                        return await stealth_service.scrape(
                            url=url,
                            formats=formats,
                            only_main_content=only_main_content,
                            wait_for=wait_for,
                            timeout=timeout,
                            screenshot_full_page=screenshot_full_page,
                            actions=actions,
                            json_schema=json_schema,
                            json_prompt=json_prompt,
                            include_tags=include_tags,
                            exclude_tags=exclude_tags,
                            max_age=max_age,
                        )
                    else:
                        LOGGER.warning(f"Bot detection suspected for {url}.{_stealth_hint()}")

                # Check for CAPTCHA and solve if enabled
                captcha_detected = self._looks_like_captcha(page_content.html)
                if captcha_detected:
                    if self._solve_captcha:
                        LOGGER.info(f"CAPTCHA detected for {url}, attempting to solve...")
                        try:
                            # Need access to the page for CAPTCHA solving
                            # Re-fetch with CAPTCHA solving
                            solved_result = await self._scrape_with_captcha_solving(
                                url=url,
                                formats=formats,
                                only_main_content=only_main_content,
                                wait_for=wait_for,
                                timeout=timeout,
                                screenshot_full_page=screenshot_full_page,
                                actions=actions,
                                json_schema=json_schema,
                                json_prompt=json_prompt,
                                include_tags=include_tags,
                                exclude_tags=exclude_tags,
                            )
                            if solved_result:
                                return solved_result
                        except Exception as e:
                            LOGGER.warning(f"CAPTCHA solving failed: {e}")
                    else:
                        # Check if content was extracted successfully despite CAPTCHA element
                        content_words = len(markdown.split()) if markdown else 0
                        if content_words >= 50:
                            LOGGER.info(f"CAPTCHA element detected for {url} (content extracted successfully)")
                        else:
                            LOGGER.warning(
                                f"CAPTCHA detected for {url} - content extraction may be incomplete.{_captcha_hint()}"
                            )

                if "html" in formats:
                    # Clean HTML (boilerplate removed)
                    html = self._get_clean_html(
                        page_content.html, only_main_content, include_tags=include_tags, exclude_tags=exclude_tags
                    )

                if "rawHtml" in formats:
                    raw_html = page_content.html

                if "links" in formats:
                    links = await browser.extract_links(url)

                if "images" in formats:
                    images = await browser.extract_images(page_content.html, url)

                if "branding" in formats:
                    # Extract branding information
                    from supacrawl.services.branding import BrandingExtractor

                    extractor = BrandingExtractor()
                    branding = extractor.extract(page_content.html, url)

                if capture_screenshot and page_content.screenshot:
                    screenshot_b64 = base64.b64encode(page_content.screenshot).decode("utf-8")

                if capture_pdf and page_content.pdf:
                    pdf_b64 = base64.b64encode(page_content.pdf).decode("utf-8")

                if "json" in formats:
                    # Perform LLM extraction
                    json_data = await self._extract_json(
                        markdown or "",
                        json_schema,
                        json_prompt,
                    )

                if "summary" in formats:
                    # Generate LLM summary of the page content
                    summary = await self._generate_summary(markdown or "")

                # Compute word count from markdown
                word_count = len(markdown.split()) if markdown else None

                # Process action results (screenshots and scrapes)
                actions_output = self._process_action_results(
                    page_content.action_results,
                    only_main_content=only_main_content,
                    include_tags=include_tags,
                    exclude_tags=exclude_tags,
                )

                result = ScrapeResult(
                    success=True,
                    data=ScrapeData(  # type: ignore[call-arg]
                        markdown=markdown,
                        html=html,
                        raw_html=raw_html,
                        screenshot=screenshot_b64,
                        pdf=pdf_b64,
                        llm_extraction=json_data,
                        summary=summary,
                        metadata=ScrapeMetadata(
                            # Core metadata
                            title=metadata.title,
                            description=metadata.description,
                            language=metadata.language,
                            keywords=metadata.keywords,
                            robots=metadata.robots,
                            canonical_url=metadata.canonical_url,
                            # OpenGraph metadata
                            og_title=metadata.og_title,
                            og_description=metadata.og_description,
                            og_image=metadata.og_image,
                            og_url=metadata.og_url,
                            og_site_name=metadata.og_site_name,
                            # Source information
                            source_url=url,
                            status_code=page_content.status_code,
                            # Detected timezone
                            timezone=metadata.timezone,
                            # Content metrics
                            word_count=word_count,
                        ),
                        links=links,
                        images=images,
                        branding=branding,
                        actions=actions_output,
                    ),
                )

                # Store in cache if max_age > 0 and cache is configured
                if max_age > 0 and self._cache:
                    self._cache.set(url, result.model_dump(), max_age)

                return result

            finally:
                if owns_browser and browser:
                    await browser.__aexit__(None, None, None)

        except Exception as e:
            error_msg = str(e)

            # Add stealth hint for common bot-detection related errors
            if not self._stealth and any(
                pattern in error_msg.lower() for pattern in ["403", "429", "timeout", "blocked", "denied"]
            ):
                error_msg += _stealth_hint()

            LOGGER.error(f"Scrape failed for {url}: {e}", exc_info=True)
            return ScrapeResult(
                success=False,
                error=error_msg,
            )

    def _get_clean_html(
        self,
        html: str,
        only_main_content: bool,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> str:
        """Get cleaned HTML with boilerplate removed.

        Args:
            html: Raw HTML
            only_main_content: Extract main content only
            include_tags: CSS selectors for elements to include
            exclude_tags: CSS selectors for elements to exclude

        Returns:
            Cleaned HTML string
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove boilerplate
        for tag_name in ["script", "style", "nav", "footer", "header", "noscript", "iframe"]:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Apply exclude_tags first
        if exclude_tags:
            for selector in exclude_tags:
                try:
                    for element in soup.select(selector):
                        element.decompose()
                except Exception:
                    pass  # Invalid selector, skip

        # Apply include_tags if specified (takes precedence over only_main_content)
        if include_tags:
            matched_elements: list[Any] = []
            for selector in include_tags:
                try:
                    matched_elements.extend(soup.select(selector))
                except Exception:
                    pass  # Invalid selector, skip

            if matched_elements:
                # Create wrapper with matched elements
                wrapper = soup.new_tag("div")
                for element in matched_elements:
                    if element not in [wrapper] + list(wrapper.descendants):
                        wrapper.append(element.extract())
                return str(wrapper)

        # Find main content if requested
        if only_main_content:
            for selector in ["main", "article", "[role='main']", ".content", "#content"]:
                main = soup.select_one(selector)
                if main:
                    return str(main)

        body = soup.find("body")
        return str(body) if body else str(soup)

    async def _extract_json(
        self,
        markdown: str,
        schema: dict[str, Any] | None,
        prompt: str | None,
    ) -> dict[str, Any] | None:
        """Extract structured JSON data from markdown using LLM.

        Args:
            markdown: Markdown content to extract from
            schema: JSON schema for structured extraction
            prompt: Custom extraction prompt

        Returns:
            Extracted JSON data or None on failure
        """
        from supacrawl.services.extract import ExtractService

        # Create ExtractService with self as scrape service
        # We need to avoid circular calls, so we create a minimal scrape wrapper
        class NoOpScrapeService:
            """Wrapper that returns markdown directly without scraping."""

            async def scrape(self, url: str, **kwargs):
                from supacrawl.models import ScrapeData, ScrapeMetadata, ScrapeResult

                return ScrapeResult(
                    success=True,
                    data=ScrapeData(  # type: ignore[call-arg]
                        markdown=markdown,
                        metadata=ScrapeMetadata(),
                    ),
                )

        extract_service = ExtractService(
            scrape_service=NoOpScrapeService(),  # type: ignore[arg-type]
        )

        try:
            # Call extraction with dummy URL (we already have the content)
            result = await extract_service.extract(
                urls=["dummy://content"],
                prompt=prompt,
                schema=schema,
            )

            if result.success and result.data and len(result.data) > 0:
                item = result.data[0]
                if item.success and item.data:
                    return item.data

            LOGGER.warning("JSON extraction failed or returned no data")
            return None

        except Exception as e:
            LOGGER.error(f"JSON extraction error: {e}", exc_info=True)
            return None

    async def _generate_summary(self, markdown: str) -> str | None:
        """Generate a concise LLM summary of the page content.

        Args:
            markdown: Markdown content to summarise

        Returns:
            2-3 sentence summary or None if LLM not configured or on failure
        """
        if not markdown.strip():
            return None

        # Limit content to avoid context overflow (~10k chars as per issue spec)
        max_content = 10000
        content = markdown[:max_content]
        if len(markdown) > max_content:
            content += "\n\n[Content truncated...]"

        from supacrawl.llm import LLMClient, LLMNotConfiguredError, load_llm_config

        # Load config - return None if LLM not configured (summary is optional)
        try:
            config = load_llm_config()
        except LLMNotConfiguredError:
            LOGGER.warning("LLM not configured, skipping summary generation")
            return None

        client = LLMClient(config)

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a summarisation assistant. Your task is to provide "
                        "concise summaries of web page content. Always respond with "
                        "plain text only, no markdown formatting."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Summarise the following web page content in 2-3 sentences. "
                        "Focus on the main topic and key information.\n\n"
                        f"Content:\n{content}\n\nSummary:"
                    ),
                },
            ]

            response = await client.chat(messages)

            # Clean up the response
            summary = response.strip()

            # Ensure summary is concise (under 500 chars as per issue spec)
            if len(summary) > 500:
                # Truncate to last complete sentence
                sentences = summary[:500].rsplit(".", 1)
                if len(sentences) > 1:
                    summary = sentences[0] + "."
                else:
                    summary = summary[:497] + "..."

            return summary

        except Exception as e:
            LOGGER.warning(f"Summary generation failed: {e}")
            return None
        finally:
            await client.close()

    def _process_action_results(
        self,
        action_results: list[Any] | None,
        only_main_content: bool = True,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> ActionsOutput | None:
        """Process action results to extract screenshots and scrapes.

        Args:
            action_results: List of ActionResult objects from ActionRunner
            only_main_content: Whether to extract main content for markdown conversion
            include_tags: CSS selectors for elements to include
            exclude_tags: CSS selectors for elements to exclude

        Returns:
            ActionsOutput with screenshots and scrapes, or None if no results
        """
        if not action_results:
            return None

        screenshots: list[str] = []
        scrapes: list[ScrapeActionResult] = []

        for result in action_results:
            # Handle screenshot actions
            if result.action_type == "screenshot" and result.screenshot:
                screenshot_b64 = base64.b64encode(result.screenshot).decode("utf-8")
                screenshots.append(screenshot_b64)

            # Handle scrape actions
            if result.action_type == "scrape" and result.scrape:
                # Convert HTML to markdown
                scrape_markdown = self._converter.convert(
                    result.scrape.html,
                    base_url=result.scrape.url,
                    only_main_content=only_main_content,
                    include_tags=include_tags,
                    exclude_tags=exclude_tags,
                )

                scrapes.append(
                    ScrapeActionResult(
                        url=result.scrape.url,
                        html=result.scrape.html,
                        markdown=scrape_markdown,
                    )
                )

        # Return None if no screenshots or scrapes were captured
        if not screenshots and not scrapes:
            return None

        return ActionsOutput(
            screenshots=screenshots if screenshots else None,
            scrapes=scrapes if scrapes else None,
        )

    def _looks_like_captcha(self, html: str) -> bool:
        """Detect if the page contains a CAPTCHA challenge.

        Args:
            html: Raw HTML content

        Returns:
            True if CAPTCHA is detected
        """
        captcha_patterns = [
            # reCAPTCHA
            r"g-recaptcha",
            r"grecaptcha",
            r"recaptcha/api",
            r"data-sitekey",
            # hCaptcha
            r"h-captcha",
            r"hcaptcha.com",
            r'class="h-captcha"',
            # Cloudflare Turnstile
            r"cf-turnstile",
            r"challenges.cloudflare.com/turnstile",
            # Generic CAPTCHA indicators
            r"iframe[^>]*captcha",
        ]

        import re

        for pattern in captcha_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                return True
        return False

    async def _scrape_with_captcha_solving(
        self,
        url: str,
        formats: list[Any],
        only_main_content: bool,
        wait_for: int,
        timeout: int,
        screenshot_full_page: bool,
        actions: list[Any] | None,
        json_schema: dict[str, Any] | None,
        json_prompt: str | None,
        include_tags: list[str] | None,
        exclude_tags: list[str] | None,
    ) -> ScrapeResult | None:
        """Scrape a URL with CAPTCHA solving enabled.

        This method creates a new browser context, navigates to the page,
        detects and solves any CAPTCHA, then continues scraping.

        Args:
            url: URL to scrape
            formats: Output formats
            only_main_content: Extract main content only
            wait_for: Additional wait time after page load
            timeout: Page load timeout
            screenshot_full_page: Full page screenshot
            actions: Actions to execute
            json_schema: JSON schema for extraction
            json_prompt: Prompt for JSON extraction
            include_tags: CSS selectors to include
            exclude_tags: CSS selectors to exclude

        Returns:
            ScrapeResult if successful, None if CAPTCHA solving failed
        """
        from supacrawl.services.captcha import (
            CaptchaSolver,
            CaptchaSolverError,
        )

        # Create browser context for CAPTCHA solving
        browser = BrowserManager(
            timeout_ms=timeout,
            locale_config=self._locale_config,
            stealth=self._stealth,
            proxy=self._proxy,
        )

        try:
            await browser.start()

            # Navigate to page
            if browser._browser is None:
                raise ProviderError("Browser failed to start", provider="playwright")
            context = await browser._browser.new_context(**browser._build_context_options())
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                # Detect and solve CAPTCHA
                solver = CaptchaSolver()
                try:
                    solved = await solver.detect_and_solve(page)
                    if solved:
                        LOGGER.info(f"CAPTCHA solved successfully for {url}")

                        # Wait for page to process the solution
                        await page.wait_for_load_state("networkidle", timeout=10000)

                        # Now re-scrape using the normal flow
                        # Get the new HTML after CAPTCHA is solved
                        html = await page.content()

                        # Check if CAPTCHA is still present
                        if self._looks_like_captcha(html):
                            LOGGER.warning("CAPTCHA still present after solving")
                            return None

                        # Build ScrapeResult from the solved page
                        # This is a simplified version - we could extract more data
                        markdown = self._converter.convert(
                            html,
                            base_url=url,
                            only_main_content=only_main_content,
                            include_tags=include_tags,
                            exclude_tags=exclude_tags,
                        )

                        metadata = await browser.extract_metadata(html)

                        return ScrapeResult(
                            success=True,
                            data=ScrapeData(  # type: ignore[call-arg]
                                markdown=markdown if "markdown" in formats else None,
                                html=self._get_clean_html(html, only_main_content, include_tags, exclude_tags)
                                if "html" in formats
                                else None,
                                raw_html=html if "rawHtml" in formats else None,
                                metadata=ScrapeMetadata(
                                    title=metadata.title,
                                    description=metadata.description,
                                    language=metadata.language,
                                    keywords=metadata.keywords,
                                    robots=metadata.robots,
                                    canonical_url=metadata.canonical_url,
                                    og_title=metadata.og_title,
                                    og_description=metadata.og_description,
                                    og_image=metadata.og_image,
                                    og_url=metadata.og_url,
                                    og_site_name=metadata.og_site_name,
                                    source_url=url,
                                    status_code=200,
                                    timezone=metadata.timezone,
                                    word_count=len(markdown.split()) if markdown else None,
                                ),
                            ),
                        )
                    else:
                        LOGGER.debug("No CAPTCHA found on page during solve attempt")
                        return None

                except CaptchaSolverError as e:
                    LOGGER.warning(f"CAPTCHA solving error: {e}")
                    return None

            finally:
                await page.close()

        finally:
            await browser.stop()
