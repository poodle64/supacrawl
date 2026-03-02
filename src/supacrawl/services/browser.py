"""Browser manager for Playwright-based page fetching.

ANTI-BOT PROTECTION (three tiers):

    Tier 1 - Basic stealth scripts (always active, no configuration):
        - navigator.webdriver = false (hides automation)
        - Chrome runtime objects (window.chrome.runtime, etc.)
        - Non-empty plugins array (avoids empty plugins fingerprint)
        - Standard languages array (['en-US', 'en'])
        - WebGL vendor/renderer spoofing (Intel Inc. / Intel Iris OpenGL Engine)
        - Canvas fingerprint noise (unique per session, non-destructive)
        - Standard browser headers (Accept-Language, Sec-Fetch-*, etc.)

    Tier 2 - Patchright (optional, for heavily protected sites):
        Install: pip install supacrawl[stealth]
        Usage: BrowserManager(stealth=True) or --stealth flag or --engine patchright
        Provides: Patched Chromium with enhanced anti-detection

    Tier 3 - Camoufox (optional, for Akamai and advanced bot detection):
        Install: pip install supacrawl[camoufox]
        Usage: BrowserManager(engine="camoufox") or --engine camoufox
        Provides: Patched Firefox with C++ engine-level anti-detection
        Effective against: Akamai Bot Manager, advanced TLS fingerprinting

CAPTCHA SOLVING (optional, requires third-party service):
    Install: pip install supacrawl[captcha]
    Configure: export CAPTCHA_API_KEY=your-2captcha-api-key
    Usage: ScrapeService(solve_captcha=True) or --solve-captcha flag
    Supports: reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile
    WARNING: Each solve costs ~$0.002-0.003

OTHER FEATURES:
    - Proxy support: --proxy http://user:pass@host:port or socks5://host:port
    - Locale/timezone: Automatic or via LocaleConfig
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page

LOGGER = logging.getLogger(__name__)

# Basic stealth scripts for non-stealth mode (subset of puppeteer-extra-plugin-stealth)
STEALTH_SCRIPTS = [
    # navigator.webdriver = false
    """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
    });
    """,
    # Chrome runtime objects
    """
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };
    """,
    # Plugins array (non-empty)
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    """,
    # Languages array
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
    """,
    # WebGL vendor/renderer spoofing (prevents GPU fingerprinting)
    # Safely checks if WebGL exists before patching
    """
    (function() {
        // Only patch if WebGL is available
        if (typeof WebGLRenderingContext === 'undefined') return;

        const getParameterOriginal = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            // UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            // UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameterOriginal.call(this, parameter);
        };

        // Also patch WebGL2 if available
        if (typeof WebGL2RenderingContext !== 'undefined') {
            const getParameter2Original = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter2Original.call(this, parameter);
            };
        }
    })();
    """,
    # Canvas fingerprint noise - NON-DESTRUCTIVE approach
    # Only affects the OUTPUT of toDataURL/toBlob, not the actual canvas content
    # This ensures screenshots and visual rendering are unaffected
    """
    (function() {
        // Session-stable noise seed (consistent within page, different per session)
        const noiseSeed = Math.floor(Math.random() * 1000);

        // Simple seeded random for consistent noise
        function seededRandom(seed) {
            const x = Math.sin(seed) * 10000;
            return x - Math.floor(x);
        }

        // Add subtle noise to a COPY of image data (non-destructive)
        function addNoiseToData(data, seed) {
            for (let i = 0; i < data.length; i += 4) {
                // Modify RGB channels, not alpha
                for (let c = 0; c < 3; c++) {
                    const noise = Math.floor(seededRandom(seed + i + c) * 3) - 1;
                    data[i + c] = Math.max(0, Math.min(255, data[i + c] + noise));
                }
            }
        }

        // Patch toDataURL - creates noisy copy without modifying original canvas
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
            // Only add noise for fingerprinting-relevant types
            if (!type || type === 'image/png' || type === 'image/jpeg') {
                try {
                    const context = this.getContext('2d');
                    if (context && this.width > 0 && this.height > 0) {
                        // Create a temporary canvas to avoid modifying original
                        const tempCanvas = document.createElement('canvas');
                        tempCanvas.width = this.width;
                        tempCanvas.height = this.height;
                        const tempContext = tempCanvas.getContext('2d');

                        // Copy original content
                        tempContext.drawImage(this, 0, 0);

                        // Get image data and add noise
                        const imageData = tempContext.getImageData(0, 0, this.width, this.height);
                        addNoiseToData(imageData.data, noiseSeed);
                        tempContext.putImageData(imageData, 0, 0);

                        // Return noisy version
                        return originalToDataURL.call(tempCanvas, type, quality);
                    }
                } catch (e) {
                    // Fall through to original on any error (e.g., WebGL canvas, tainted canvas)
                }
            }
            return originalToDataURL.call(this, type, quality);
        };

        // Patch toBlob - creates noisy copy without modifying original canvas
        const originalToBlob = HTMLCanvasElement.prototype.toBlob;
        HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
            if (!type || type === 'image/png' || type === 'image/jpeg') {
                try {
                    const context = this.getContext('2d');
                    if (context && this.width > 0 && this.height > 0) {
                        // Create a temporary canvas
                        const tempCanvas = document.createElement('canvas');
                        tempCanvas.width = this.width;
                        tempCanvas.height = this.height;
                        const tempContext = tempCanvas.getContext('2d');

                        // Copy and add noise
                        tempContext.drawImage(this, 0, 0);
                        const imageData = tempContext.getImageData(0, 0, this.width, this.height);
                        addNoiseToData(imageData.data, noiseSeed);
                        tempContext.putImageData(imageData, 0, 0);

                        // Return noisy version
                        return originalToBlob.call(tempCanvas, callback, type, quality);
                    }
                } catch (e) {
                    // Fall through to original
                }
            }
            return originalToBlob.call(this, callback, type, quality);
        };

        // NOTE: We intentionally do NOT patch getImageData
        // Patching getImageData breaks legitimate canvas operations (games, image editors)
        // Fingerprinting typically uses toDataURL, so this is sufficient protection
    })();
    """,
]


def _parse_proxy_url(proxy_url: str) -> dict[str, Any]:
    """Parse a proxy URL into Playwright proxy config.

    Supports formats:
        - http://host:port
        - http://user:pass@host:port
        - socks5://host:port
        - socks5://user:pass@host:port

    Args:
        proxy_url: Proxy URL string

    Returns:
        Dictionary for Playwright proxy config

    Raises:
        ValueError: If proxy URL format is invalid
    """
    # Handle socks5 scheme (Playwright expects socks5://)
    parsed = urlparse(proxy_url)

    if parsed.scheme not in ("http", "https", "socks5"):
        raise ValueError(f"Invalid proxy scheme '{parsed.scheme}'. Supported: http, https, socks5")

    # Build proxy config
    config: dict[str, Any] = {
        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}",
    }

    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password

    return config


class StealthNotAvailableError(ImportError):
    """Raised when stealth mode is requested but patchright is not installed."""

    def __init__(self) -> None:
        super().__init__("Stealth mode requires patchright. Install with: pip install supacrawl[stealth]")


class CamoufoxNotAvailableError(ImportError):
    """Raised when Camoufox engine is requested but camoufox is not installed."""

    def __init__(self) -> None:
        super().__init__("Camoufox engine requires camoufox. Install with: pip install supacrawl[camoufox]")


# Valid engine choices
ENGINE_CHOICES = ("playwright", "patchright", "camoufox")

# Domains to skip when expanding iframes (ads, analytics, tracking, CAPTCHA)
IFRAME_BLOCKED_DOMAINS = frozenset(
    {
        # Advertising
        "doubleclick.net",
        "googlesyndication.com",
        "amazon-adsystem.com",
        "adnxs.com",
        "adsrvr.org",
        "moatads.com",
        "taboola.com",
        "outbrain.com",
        # Analytics / tracking
        "google-analytics.com",
        "googletagmanager.com",
        "analytics.google.com",
        "connect.facebook.net",
        "bat.bing.com",
        "sc-static.net",
        "hotjar.com",
        "clarity.ms",
        # CAPTCHA
        "recaptcha.net",
        "hcaptcha.com",
        "challenges.cloudflare.com",
    }
)

# Maximum iframes to expand per page (performance guard)
MAX_IFRAMES_PER_PAGE = 10


def _is_blocked_iframe_domain(hostname: str) -> bool:
    """Check if hostname matches a blocked iframe domain."""
    hostname = hostname.lower()
    return any(hostname == domain or hostname.endswith("." + domain) for domain in IFRAME_BLOCKED_DOMAINS)


@dataclass
class PageContent:
    """Result of fetching a page."""

    url: str
    html: str
    title: str | None
    status_code: int
    screenshot: bytes | None = None
    pdf: bytes | None = None
    action_results: list[Any] | None = None  # Results from ActionRunner


@dataclass
class PageMetadata:
    """Metadata extracted from a page."""

    # Core metadata
    title: str | None
    description: str | None
    language: str | None
    keywords: str | None
    robots: str | None
    canonical_url: str | None

    # OpenGraph metadata
    og_title: str | None
    og_description: str | None
    og_image: str | None
    og_url: str | None
    og_site_name: str | None

    # Detected timezone (IANA format, e.g. "America/New_York")
    timezone: str | None = None


def _extract_timezone_from_jsonld(data: Any, iana_tz_pattern: re.Pattern[str]) -> str | None:
    """Recursively search JSON-LD data for IANA timezone values.

    Args:
        data: Parsed JSON-LD data (dict, list, or primitive)
        iana_tz_pattern: Compiled regex for IANA timezone identifiers

    Returns:
        IANA timezone string or None
    """
    if isinstance(data, dict):
        # Check timezone-related keys directly
        for key in ("timezone", "timeZone", "time_zone"):
            val = data.get(key)
            if isinstance(val, str):
                match = iana_tz_pattern.search(val)
                if match:
                    return match.group(0)
        # Check address/location for timezone
        for key in ("address", "location", "geo"):
            val = data.get(key)
            if isinstance(val, dict):
                result = _extract_timezone_from_jsonld(val, iana_tz_pattern)
                if result:
                    return result
        # Check @graph for nested items
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                result = _extract_timezone_from_jsonld(item, iana_tz_pattern)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_timezone_from_jsonld(item, iana_tz_pattern)
            if result:
                return result
    return None


class BrowserManager:
    """Manages Playwright browser for page fetching.

    Usage:
        async with BrowserManager() as browser:
            content = await browser.fetch_page("https://example.com")

        # With locale configuration
        from supacrawl.models import LocaleConfig
        locale = LocaleConfig.from_country("AU")
        async with BrowserManager(locale_config=locale) as browser:
            content = await browser.fetch_page("https://example.com")

        # With stealth mode (requires: pip install supacrawl[stealth])
        async with BrowserManager(stealth=True) as browser:
            content = await browser.fetch_page("https://protected-site.com")
    """

    def __init__(
        self,
        headless: bool | None = None,
        timeout_ms: int | None = None,
        user_agent: str | None = None,
        locale_config: Any | None = None,  # LocaleConfig, avoid circular import
        stealth: bool = False,
        proxy: str | None = None,
        engine: str | None = None,
    ):
        """Initialize browser manager.

        Args:
            headless: Run headless (default from SUPACRAWL_HEADLESS env, or True).
                Note: When stealth=True and headless is not explicitly set, defaults
                to False (headful) because stealth mode is more effective headful.
                Camoufox supports headless=True with humanize=True effectively.
            timeout_ms: Page load timeout (default from SUPACRAWL_TIMEOUT env, or 30000)
            user_agent: User agent string (default from SUPACRAWL_USER_AGENT env)
            locale_config: LocaleConfig for browser locale/timezone settings
            stealth: Enable stealth mode via Patchright for anti-bot evasion.
                Automatically enables headful mode unless headless is explicitly set.
                Ignored when engine is explicitly set.
            proxy: Proxy URL (e.g., http://user:pass@host:port, socks5://host:port)
            engine: Browser engine to use. Options:
                - "playwright" (default): Standard Playwright Chromium with basic stealth scripts
                - "patchright": Patched Chromium via Patchright (Tier 2 anti-detection)
                - "camoufox": Patched Firefox via Camoufox (Tier 3 anti-detection,
                  effective against Akamai Bot Manager)
                When not set, falls back to "patchright" if stealth=True, else "playwright".
        """
        # Resolve engine from explicit engine param, stealth flag, or default
        if engine is not None:
            if engine not in ENGINE_CHOICES:
                raise ValueError(f"Invalid engine '{engine}'. Choose from: {', '.join(ENGINE_CHOICES)}")
            self.engine = engine
        elif stealth:
            self.engine = "patchright"
        else:
            self.engine = "playwright"

        # Keep stealth flag for backwards compat (True when engine is patchright or camoufox)
        self.stealth = self.engine in ("patchright", "camoufox")

        # Headless defaults: Patchright prefers headful, Camoufox works headless
        if headless is not None:
            self.headless = headless
        elif self.engine == "patchright":
            # Patchright + headless has worse detection scores than headful
            self.headless = self._env_bool("SUPACRAWL_HEADLESS", False)
        elif self.engine == "camoufox":
            # Camoufox works well headless with humanize=True
            self.headless = self._env_bool("SUPACRAWL_HEADLESS", True)
        else:
            self.headless = self._env_bool("SUPACRAWL_HEADLESS", True)

        self.timeout_ms = timeout_ms or int(os.getenv("SUPACRAWL_TIMEOUT", "30000"))
        # Only set user_agent if explicitly provided or env var is set
        # Otherwise let Playwright use its real browser UA (reduces fingerprint mismatch)
        # Note: Camoufox generates its own fingerprint, so user_agent is not set for it
        self.user_agent = user_agent or os.getenv("SUPACRAWL_USER_AGENT")
        self.locale_config = locale_config
        self.proxy = proxy or os.getenv("SUPACRAWL_PROXY")
        self._browser: Browser | None = None
        self._playwright: Any = None

    @staticmethod
    def _env_bool(key: str, default: bool) -> bool:
        """Get boolean from environment variable."""
        val = os.getenv(key)
        if val is None:
            return default
        return val.strip().lower() in {"1", "true", "yes", "on"}

    def _resolve_device_config(self, device: str) -> dict[str, Any]:
        """Resolve a Playwright device name to context options.

        Looks up the device in Playwright's built-in device descriptors and
        returns a dict suitable for passing to ``browser.new_context()``.

        Args:
            device: Device name (e.g. "iPhone 14", "Pixel 7").

        Returns:
            Dict with user_agent, viewport, device_scale_factor, is_mobile,
            has_touch keys.

        Raises:
            ValueError: If the device name is not found in Playwright's
                device descriptors.
        """
        if self._playwright is None:
            raise RuntimeError("Playwright not started. Cannot resolve device config.")

        devices = self._playwright.devices
        if device not in devices:
            # Build helpful error with close matches
            available = sorted(devices.keys())
            lower = device.lower()
            suggestions = [d for d in available if lower in d.lower() or d.lower() in lower][:5]
            hint = f" Did you mean: {', '.join(suggestions)}" if suggestions else ""
            raise ValueError(
                f"Unknown device '{device}'. Use BrowserManager.list_devices() to see available devices.{hint}"
            )

        config = dict(devices[device])
        # Remove default_browser_type — it's metadata, not a context option
        config.pop("default_browser_type", None)
        return config

    async def list_devices(self) -> list[str]:
        """Return sorted list of available Playwright device names.

        Requires the browser to be started (Playwright instance available).
        """
        if self._playwright is None:
            raise RuntimeError("Playwright not started. Call start() first.")
        return sorted(self._playwright.devices.keys())

    def _build_context_options(self, device: str | None = None) -> dict[str, Any]:
        """Build browser context options including locale and device settings.

        When no explicit configuration is provided, returns minimal options
        to let Playwright use browser defaults. This reduces fingerprint
        mismatch that can trigger bot detection.

        Args:
            device: Optional Playwright device name for mobile emulation
                (e.g. "iPhone 14", "Pixel 7").

        Returns:
            Dictionary of options for browser.new_context()
        """
        options: dict[str, Any] = {}

        # Apply device emulation first (provides base viewport, UA, etc.)
        if device:
            device_config = self._resolve_device_config(device)
            options.update(device_config)
            LOGGER.debug("Applying device emulation: %s", device)

        # Only set user agent if explicitly provided (reduces fingerprint mismatch)
        # When device emulation is active, the device's UA is already set above;
        # an explicit user_agent overrides it (intentional user choice).
        if self.user_agent:
            options["user_agent"] = self.user_agent

        # Apply locale config if explicitly provided
        if self.locale_config is not None:
            locale = self.locale_config.get_language()
            timezone = self.locale_config.get_timezone()
            accept_lang = self.locale_config.get_accept_language_header()

            options["locale"] = locale
            options["timezone_id"] = timezone
            options["extra_http_headers"] = {
                "Accept-Language": accept_lang,
            }
            LOGGER.debug(
                "Using locale config: language=%s, timezone=%s",
                locale,
                timezone,
            )
        else:
            # Check for explicit environment variable configuration
            locale_env = os.getenv("SUPACRAWL_LOCALE")
            timezone_env = os.getenv("SUPACRAWL_TIMEZONE")

            # Only set if explicitly configured via env vars
            if locale_env:
                options["locale"] = locale_env
            if timezone_env:
                options["timezone_id"] = timezone_env

        return options

    async def __aenter__(self) -> "BrowserManager":
        """Start browser (async context manager entry)."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close browser (async context manager exit)."""
        await self.stop()

    def _get_playwright_module(self) -> Any:
        """Get the appropriate playwright module based on engine setting.

        Returns:
            The async_playwright function from either patchright or playwright.
            Returns None when engine is "camoufox" (uses separate launch path).

        Raises:
            StealthNotAvailableError: If patchright engine requested but not installed.
            CamoufoxNotAvailableError: If camoufox engine requested but not installed.
        """
        if self.engine == "camoufox":
            # Camoufox has its own launch path, validated in start()
            try:
                import camoufox  # noqa: F401

                LOGGER.debug("Using Camoufox engine (patched Firefox)")
                return None  # Camoufox doesn't use async_playwright
            except ImportError as e:
                raise CamoufoxNotAvailableError() from e
        elif self.engine == "patchright":
            try:
                from patchright.async_api import async_playwright

                LOGGER.debug("Using Patchright engine (patched Chromium)")
                return async_playwright
            except ImportError as e:
                raise StealthNotAvailableError() from e
        else:
            from playwright.async_api import async_playwright  # type: ignore[assignment]

            return async_playwright

    async def start(self) -> None:
        """Start the browser.

        Can be called directly for manual lifecycle management, or implicitly
        via async context manager (async with BrowserManager() as browser).

        Raises:
            StealthNotAvailableError: If patchright engine requested but not installed.
            CamoufoxNotAvailableError: If camoufox engine requested but not installed.
        """
        if self._browser is not None:
            return  # Already started

        if self.engine == "camoufox":
            await self._start_camoufox()
        else:
            await self._start_playwright()

    async def _start_playwright(self) -> None:
        """Start browser via Playwright or Patchright."""
        async_playwright = self._get_playwright_module()
        self._playwright = await async_playwright().start()

        # Build launch options
        launch_options: dict[str, Any] = {"headless": self.headless}

        # Add proxy if configured
        if self.proxy:
            try:
                launch_options["proxy"] = _parse_proxy_url(self.proxy)
                LOGGER.debug("Using proxy: %s", self.proxy.split("@")[-1])  # Hide credentials
            except ValueError as e:
                LOGGER.error(f"Invalid proxy URL: {e}")
                raise

        self._browser = await self._playwright.chromium.launch(**launch_options)
        LOGGER.debug(
            "Browser started (engine=%s, headless=%s, proxy=%s)",
            self.engine,
            self.headless,
            bool(self.proxy),
        )

    async def _start_camoufox(self) -> None:
        """Start browser via Camoufox (patched Firefox).

        Camoufox provides AsyncCamoufox, an async context manager that
        handles Playwright acquisition internally and returns a browser
        instance compatible with the Playwright API.
        """
        try:
            from camoufox.async_api import AsyncCamoufox
        except ImportError as e:
            raise CamoufoxNotAvailableError() from e

        # Build Camoufox options
        camoufox_options: dict[str, Any] = {
            "headless": self.headless,
            "humanize": True,  # Natural cursor movement
        }

        # Add proxy if configured
        if self.proxy:
            try:
                camoufox_options["proxy"] = _parse_proxy_url(self.proxy)
                LOGGER.debug("Using proxy: %s", self.proxy.split("@")[-1])
            except ValueError as e:
                LOGGER.error(f"Invalid proxy URL: {e}")
                raise

        # Apply locale if configured
        if self.locale_config is not None:
            locale = self.locale_config.get_language()
            if locale:
                camoufox_options["locale"] = locale

        # Camoufox returns a context manager; we enter it and store the browser
        self._camoufox_cm = AsyncCamoufox(**camoufox_options)
        self._browser = await self._camoufox_cm.__aenter__()

        LOGGER.debug(
            "Browser started (engine=camoufox, headless=%s, humanize=True, proxy=%s)",
            self.headless,
            bool(self.proxy),
        )

    async def stop(self) -> None:
        """Stop the browser and cleanup resources.

        Safe to call multiple times.
        """
        if self.engine == "camoufox" and hasattr(self, "_camoufox_cm"):
            # Camoufox cleanup via its context manager
            try:
                await self._camoufox_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._browser = None
            del self._camoufox_cm
        else:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        LOGGER.debug("Browser stopped")

    async def fetch_page(
        self,
        url: str,
        wait_for_spa: bool = True,
        spa_timeout_ms: int = 5000,
        capture_screenshot: bool = False,
        capture_pdf: bool = False,
        screenshot_full_page: bool = True,
        actions: list[Any] | None = None,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None = None,
        expand_iframes: Literal["none", "same-origin", "all"] = "same-origin",
        device: str | None = None,
    ) -> PageContent:
        """Fetch a page with browser rendering.

        Args:
            url: URL to fetch
            wait_for_spa: Wait for SPA content to stabilize
            spa_timeout_ms: Max time to wait for SPA stability
            capture_screenshot: Capture PNG screenshot of page
            capture_pdf: Generate PDF of page
            screenshot_full_page: Capture full scrollable page (default True)
            actions: List of Action objects to execute before capturing content
            wait_until: Page load strategy. Options: commit, domcontentloaded (default),
                load, networkidle. Falls back to SUPACRAWL_WAIT_UNTIL env var if None.
            expand_iframes: Iframe expansion mode. "none" strips all iframes (legacy),
                "same-origin" expands same-origin iframes inline (default),
                "all" expands all non-blocked iframes including cross-origin.
            device: Playwright device name for mobile emulation (e.g. "iPhone 14",
                "Pixel 7"). Sets viewport, user agent, device scale factor, and
                touch support. Not supported with the Camoufox engine.

        Returns:
            PageContent with HTML, metadata, and optional screenshot/PDF

        Raises:
            RuntimeError: If browser not initialized or fetch fails
            ValueError: If device is specified with Camoufox engine or device
                name is not recognised.
        """
        if not self._browser:
            raise RuntimeError("Browser not initialized. Use 'async with BrowserManager()' context manager.")

        if device and self.engine == "camoufox":
            raise ValueError(
                "Device emulation is not supported with the Camoufox engine. "
                "Camoufox generates its own fingerprint. Use --engine playwright or --engine patchright."
            )

        context: BrowserContext | None = None
        page: Page | None = None
        # Camoufox browser IS the context — don't create a separate one
        owns_context = self.engine != "camoufox"

        try:
            if owns_context:
                # Playwright/Patchright: create fresh context for isolation
                context_options = self._build_context_options(device=device)
                context = await self._browser.new_context(**context_options)

                # Inject stealth scripts at context level so all pages inherit them.
                # Patchright and Camoufox handle anti-detection at the engine level.
                if self.engine == "playwright":
                    for script in STEALTH_SCRIPTS:
                        await context.add_init_script(script)
                    LOGGER.debug("Injected %d stealth scripts at context level", len(STEALTH_SCRIPTS))

                page = await context.new_page()
            else:
                # Camoufox: browser is already a context, just create a page
                page = await self._browser.new_page()

            # Navigate to URL - use parameter if provided, else fall back to env var
            if wait_until is None:
                wait_until_env = os.getenv("SUPACRAWL_WAIT_UNTIL", "domcontentloaded")
                wait_until_resolved: Literal["commit", "domcontentloaded", "load", "networkidle"] = (
                    wait_until_env  # type: ignore[assignment]
                    if wait_until_env in ("commit", "domcontentloaded", "load", "networkidle")
                    else "domcontentloaded"
                )
            else:
                wait_until_resolved = wait_until
            response = await page.goto(url, wait_until=wait_until_resolved, timeout=self.timeout_ms)

            # Wait for SPA stability if requested
            # Skip if using networkidle - it already waits for JS to finish
            # and the extra polling can trigger bot detection
            if wait_for_spa and wait_until_resolved != "networkidle":
                await self._wait_for_spa_stability(page, spa_timeout_ms)

            # Execute actions if provided
            action_results_list: list[Any] | None = None
            if actions:
                from supacrawl.services.actions import ActionRunner

                runner = ActionRunner(timeout_ms=self.timeout_ms)
                action_results_list = await runner.run(page, actions)
                LOGGER.debug(f"Executed {len(action_results_list)} actions")

            # Expand iframe content inline before extracting HTML
            if expand_iframes != "none":
                await self._expand_iframes(page, mode=expand_iframes)

            # Extract HTML and title
            html = await page.content()
            title = await page.title() or None
            status_code = response.status if response else 200

            # Capture screenshot if requested
            screenshot_bytes: bytes | None = None
            if capture_screenshot:
                screenshot_bytes = await page.screenshot(
                    full_page=screenshot_full_page,
                    type="png",
                )

            # Generate PDF if requested
            # Note: page.pdf() is only available on Chromium (Playwright/Patchright),
            # not on Firefox (Camoufox). Log a warning instead of crashing.
            pdf_bytes: bytes | None = None
            if capture_pdf:
                if self.engine == "camoufox":
                    LOGGER.warning("PDF generation is not supported with Camoufox (Firefox). Skipping PDF capture.")
                else:
                    pdf_bytes = await page.pdf(
                        format="A4",
                        print_background=True,
                    )

            return PageContent(
                url=url,
                html=html,
                title=title,
                status_code=status_code,
                screenshot=screenshot_bytes,
                pdf=pdf_bytes,
                action_results=action_results_list,
            )

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if owns_context and context:
                try:
                    await context.close()
                except Exception:
                    pass

    async def _expand_iframes(
        self,
        page: Page,
        mode: Literal["same-origin", "all"] = "same-origin",
    ) -> int:
        """Expand iframe content inline in the page DOM.

        Replaces ``<iframe>`` elements with ``<div>`` wrappers containing the
        frame body HTML so that the content is captured by ``page.content()``.

        Args:
            page: Playwright page with loaded content
            mode: "same-origin" expands only same-origin frames,
                  "all" expands all non-blocked frames

        Returns:
            Number of iframes expanded
        """
        page_origin = urlparse(page.url).scheme + "://" + urlparse(page.url).netloc

        # Process frames innermost-first so nested content is captured
        frames = list(page.frames)
        frames.reverse()

        expanded = 0

        for frame in frames:
            if frame == page.main_frame:
                continue
            if expanded >= MAX_IFRAMES_PER_PAGE:
                LOGGER.debug("Reached max iframe expansion limit (%d)", MAX_IFRAMES_PER_PAGE)
                break

            frame_url = frame.url
            if not frame_url or frame_url == "about:blank":
                continue

            # Check blocked domains
            frame_hostname = urlparse(frame_url).hostname or ""
            if _is_blocked_iframe_domain(frame_hostname):
                LOGGER.debug("Skipping blocked iframe domain: %s", frame_hostname)
                continue

            # Same-origin check
            if mode == "same-origin":
                frame_origin = urlparse(frame_url).scheme + "://" + urlparse(frame_url).netloc
                if frame_origin != page_origin:
                    continue

            try:
                iframe_element = await frame.frame_element()

                # Skip tracking pixels (very small iframes)
                bounding = await iframe_element.bounding_box()
                if bounding and (bounding["width"] <= 5 or bounding["height"] <= 5):
                    LOGGER.debug("Skipping tracking-pixel iframe: %s", frame_url)
                    continue

                # Extract frame body content
                body_html = await frame.evaluate("document.body ? document.body.innerHTML : ''")
                if not body_html or not body_html.strip():
                    continue

                # Replace the <iframe> element with a <div> containing the content
                await iframe_element.evaluate(
                    """(el, args) => {
                        const [bodyHtml, src, hostname] = args;
                        const wrapper = document.createElement('div');
                        wrapper.setAttribute('data-sc-iframe-src', src);
                        const marker = document.createElement('p');
                        marker.innerHTML = '<em>[Embedded content from ' + hostname + ']</em>';
                        wrapper.appendChild(marker);
                        const content = document.createElement('div');
                        content.innerHTML = bodyHtml;
                        wrapper.appendChild(content);
                        el.replaceWith(wrapper);
                    }""",
                    [body_html, frame_url, frame_hostname],
                )
                expanded += 1

            except Exception as e:
                LOGGER.debug("Could not expand iframe %s: %s", frame_url, e)
                continue

        if expanded > 0:
            LOGGER.info("Expanded %d iframe(s) inline", expanded)
        return expanded

    async def extract_links(
        self,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None = None,
    ) -> list[str]:
        """Extract all links from a rendered page.

        Args:
            url: URL to fetch and extract links from
            wait_until: Page load strategy. Options: commit, domcontentloaded (default),
                load, networkidle. Falls back to SUPACRAWL_WAIT_UNTIL env var if None.

        Returns:
            List of absolute URLs found on the page

        Raises:
            RuntimeError: If browser not initialized or fetch fails
        """
        if not self._browser:
            raise RuntimeError("Browser not initialized. Use 'async with BrowserManager()' context manager.")

        context: BrowserContext | None = None
        page: Page | None = None
        owns_context = self.engine != "camoufox"

        try:
            if owns_context:
                context_options = self._build_context_options()
                context = await self._browser.new_context(**context_options)

                if self.engine == "playwright":
                    for script in STEALTH_SCRIPTS:
                        await context.add_init_script(script)
                    LOGGER.debug("Injected %d stealth scripts at context level", len(STEALTH_SCRIPTS))

                page = await context.new_page()
            else:
                page = await self._browser.new_page()

            # Navigate to URL - use parameter if provided, else fall back to env var
            if wait_until is None:
                wait_until_env = os.getenv("SUPACRAWL_WAIT_UNTIL", "domcontentloaded")
                wait_until_resolved: Literal["commit", "domcontentloaded", "load", "networkidle"] = (
                    wait_until_env  # type: ignore[assignment]
                    if wait_until_env in ("commit", "domcontentloaded", "load", "networkidle")
                    else "domcontentloaded"
                )
            else:
                wait_until_resolved = wait_until
            await page.goto(url, wait_until=wait_until_resolved, timeout=self.timeout_ms)

            # Extract all links using JavaScript
            links = await page.evaluate(
                """
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    return anchors.map(a => a.href).filter(href => href && href.startsWith('http'));
                }
            """
            )

            return links

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if owns_context and context:
                try:
                    await context.close()
                except Exception:
                    pass

    async def extract_images(self, html: str, base_url: str) -> list[str]:
        """Extract all image URLs from HTML content.

        Extracts from ``<img>`` tags, ``<picture>``/``<source>`` tags, and
        CSS ``background-image`` declarations (both inline styles and
        ``<style>`` blocks).

        Args:
            html: HTML content to extract images from
            base_url: Base URL for resolving relative URLs

        Returns:
            List of absolute image URLs, deduplicated and sorted
        """
        import re
        from urllib.parse import urljoin

        soup = BeautifulSoup(html, "html.parser")
        images: set[str] = set()

        # Extract from <img> tags
        for img in soup.find_all("img"):
            # Get src attribute
            src = img.get("src")
            if src and isinstance(src, str) and not src.startswith("data:"):
                absolute_url = urljoin(base_url, src)
                images.add(absolute_url)

            # Get srcset attribute (responsive images)
            srcset = img.get("srcset")
            if srcset and isinstance(srcset, str):
                for part in srcset.split(","):
                    url = part.strip().split()[0]  # Take URL, ignore size descriptor
                    if url and not url.startswith("data:"):
                        absolute_url = urljoin(base_url, url)
                        images.add(absolute_url)

        # Extract from <picture> <source> tags
        for source in soup.find_all("source"):
            # Get srcset attribute
            srcset = source.get("srcset")
            if srcset and isinstance(srcset, str):
                for part in srcset.split(","):
                    url = part.strip().split()[0]
                    if url and not url.startswith("data:"):
                        absolute_url = urljoin(base_url, url)
                        images.add(absolute_url)

            # Get src attribute (some sources use src instead of srcset)
            src = source.get("src")
            if src and isinstance(src, str) and not src.startswith("data:"):
                absolute_url = urljoin(base_url, src)
                images.add(absolute_url)

        # Extract from CSS background-image declarations
        bg_url_pattern = re.compile(r"""background(?:-image)?\s*:[^;]*url\(\s*(['"]?)(.*?)\1\s*\)""")

        # Inline style attributes on elements
        for el in soup.find_all(style=True):
            style = el.get("style", "")
            if isinstance(style, str):
                for match in bg_url_pattern.finditer(style):
                    url = match.group(2).strip()
                    if url and not url.startswith("data:"):
                        images.add(urljoin(base_url, url))

        # <style> blocks
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                for match in bg_url_pattern.finditer(style_tag.string):
                    url = match.group(2).strip()
                    if url and not url.startswith("data:"):
                        images.add(urljoin(base_url, url))

        # Filter out common tracking pixels and tiny images
        filtered_images = []
        for url in images:
            # Skip common tracking pixel patterns
            if any(pattern in url.lower() for pattern in ["1x1", "pixel", "tracking", "analytics"]):
                continue
            filtered_images.append(url)

        return sorted(filtered_images)

    @staticmethod
    def _extract_head_section(html: str) -> str:
        """Extract the head section from HTML for lightweight metadata parsing.

        Includes everything from document start through ``</head>``, which
        captures ``<html lang="...">`` and the full ``<head>`` block. Falls
        back to the full HTML if ``<head>`` boundaries are not found.
        """
        head_end = html.lower().find("</head>")
        if head_end == -1:
            return html
        return html[: head_end + len("</head>")]

    async def extract_metadata(self, html: str) -> PageMetadata:
        """Extract metadata from HTML.

        Only parses the ``<head>`` section for efficiency, since all metadata
        tags (title, meta, link, structured data) appear there.

        Args:
            html: HTML content

        Returns:
            PageMetadata with title, description, og tags, and other metadata
        """
        head_html = self._extract_head_section(html)
        soup = BeautifulSoup(head_html, "html.parser")

        def get_meta_content(name: str | None = None, property: str | None = None) -> str | None:
            """Helper to extract meta tag content."""
            if name:
                tag = soup.find("meta", attrs={"name": name})
            elif property:
                tag = soup.find("meta", attrs={"property": property})
            else:
                return None
            if not tag:
                return None
            content = tag.get("content", None)
            # Handle case where content could be a list
            if isinstance(content, list):
                return content[0] if content else None
            return content

        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        # Extract core metadata
        description = get_meta_content(name="description")
        keywords = get_meta_content(name="keywords")
        robots = get_meta_content(name="robots")

        # Extract language from html tag
        html_tag = soup.find("html")
        language_attr = html_tag.get("lang", None) if html_tag else None
        language = language_attr[0] if isinstance(language_attr, list) else language_attr

        # Extract canonical URL
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        canonical_attr = canonical_tag.get("href", None) if canonical_tag else None
        canonical_url = canonical_attr[0] if isinstance(canonical_attr, list) else canonical_attr

        # Extract OpenGraph tags
        og_title = get_meta_content(property="og:title")
        og_description = get_meta_content(property="og:description")
        og_image = get_meta_content(property="og:image")
        og_url = get_meta_content(property="og:url")
        og_site_name = get_meta_content(property="og:site_name")

        # Extract Twitter Card tags
        twitter_title = get_meta_content(name="twitter:title")
        twitter_description = get_meta_content(name="twitter:description")
        twitter_image = get_meta_content(name="twitter:image")

        # Apply title fallback: <title> → og:title → twitter:title
        effective_title = title or og_title or twitter_title

        # Apply description fallback: <meta description> → og:description → twitter:description
        effective_description = description or og_description or twitter_description

        # Detect timezone from structured data
        detected_timezone = self._detect_timezone(soup)

        return PageMetadata(
            title=effective_title,
            description=effective_description,
            language=language,
            keywords=keywords,
            robots=robots,
            canonical_url=canonical_url,
            og_title=og_title,
            og_description=og_description,
            og_image=og_image or twitter_image,
            og_url=og_url,
            og_site_name=og_site_name,
            timezone=detected_timezone,
        )

    @staticmethod
    def _detect_timezone(soup: BeautifulSoup) -> str | None:
        """Detect timezone from page structured data.

        Checks JSON-LD structured data and meta tags for IANA timezone identifiers.

        Args:
            soup: Parsed HTML

        Returns:
            IANA timezone string (e.g. "America/New_York") or None
        """
        # Pattern for IANA timezone identifiers (e.g. America/New_York, Europe/London)
        iana_tz_pattern = re.compile(
            r"\b(Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific)"
            r"/[A-Z][a-zA-Z_]+(?:/[A-Z][a-zA-Z_]+)?\b"
        )

        # 1. Check JSON-LD structured data for timezone fields
        for script_tag in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                text = script_tag.get_text(strip=True)
                if not text:
                    continue
                data = json.loads(text)
                tz = _extract_timezone_from_jsonld(data, iana_tz_pattern)
                if tz:
                    return tz
            except (json.JSONDecodeError, TypeError):
                continue

        # 2. Check meta tags for timezone info
        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "").lower()
            content = tag.get("content", "")
            if isinstance(content, list):
                content = content[0] if content else ""
            if not content:
                continue

            # Check for timezone-related meta names
            if "timezone" in name or "tz" == name:
                match = iana_tz_pattern.search(content)
                if match:
                    return match.group(0)
                # Accept raw value if it looks like an IANA timezone
                if "/" in content and len(content) < 40:
                    return content.strip()

        return None

    async def _wait_for_spa_stability(
        self,
        page: Page,
        timeout_ms: int = 5000,
    ) -> None:
        """Wait for SPA content to stop changing.

        Checks DOM content hash every 200ms, considers stable after
        3 consecutive identical hashes.

        Args:
            page: Playwright page instance
            timeout_ms: Maximum wait time in milliseconds
        """
        start_time = asyncio.get_event_loop().time()
        max_wait = timeout_ms / 1000

        # Wait for at least one heading to appear
        try:
            await page.wait_for_selector("h1, h2, main, article", timeout=timeout_ms)
        except Exception:
            # If no heading found, continue anyway
            pass

        # Wait for content stability (DOM not changing)
        last_content_hash = ""
        stable_count = 0
        required_stable = 3  # Need 3 consecutive stable checks (600ms total)

        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                # Get current page content hash
                content = await page.content()
                current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

                if current_hash == last_content_hash:
                    stable_count += 1
                    if stable_count >= required_stable:
                        LOGGER.debug(f"SPA content stable after {stable_count} checks")
                        return
                else:
                    stable_count = 0
                    last_content_hash = current_hash

                await asyncio.sleep(0.2)  # Check every 200ms
            except Exception as e:
                LOGGER.warning(f"Error checking content stability: {e}")
                break

        LOGGER.debug("SPA content wait timed out, proceeding anyway")
