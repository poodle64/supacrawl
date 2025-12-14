"""Data models for web-scraper."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from web_scraper.exceptions import ValidationError, generate_correlation_id


class OutputFormat(str, Enum):
    """Supported output formats for corpus pages.

    These formats determine what files are written to the corpus snapshot.
    """

    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"
    JSON = "json"

    @classmethod
    def from_string(cls, value: str) -> "OutputFormat":
        """Parse format from string, case-insensitive."""
        value_lower = value.lower().strip()
        # Handle common aliases
        aliases = {
            "md": cls.MARKDOWN,
            "htm": cls.HTML,
            "txt": cls.TEXT,
        }
        if value_lower in aliases:
            return aliases[value_lower]
        return cls(value_lower)

    @property
    def extension(self) -> str:
        """Get file extension for this format."""
        return {
            OutputFormat.MARKDOWN: ".md",
            OutputFormat.HTML: ".html",
            OutputFormat.TEXT: ".txt",
            OutputFormat.JSON: ".json",
        }[self]


def _brisbane_now() -> datetime:
    """
    Return the current time in Australia/Brisbane.

    Returns:
        Current datetime in Australia/Brisbane timezone.
    """
    return datetime.now(ZoneInfo("Australia/Brisbane"))


class CleaningConfig(BaseModel):
    """Configuration for content cleaning rules.

    These patterns are used to filter out trackers, navigation,
    and boilerplate content from scraped markdown.
    """

    model_config = ConfigDict(extra="forbid")

    # URL substrings that indicate tracking/analytics (filter out images/links containing these)
    tracker_patterns: list[str] = Field(
        default_factory=lambda: [
            "googleads.g.doubleclick.net",
            "doubleclick.net",
            "google-analytics.com",
            "facebook.com/tr",
            "bat.bing.com",
        ]
    )

    # Prefixes to strip from lines (e.g., markdown image/link patterns)
    strip_prefixes: list[str] = Field(
        default_factory=lambda: ["![]((", "[![]("]
    )

    # Text markers that indicate end of main content (stop processing after)
    stop_markers: list[str] = Field(
        default_factory=lambda: [
            "Build with Meta",
            "Terms and policies",
            "Privacy Policy",
            "Cookie Policy",
            "© 2024",
            "© 2025",
        ]
    )

    # Text markers that indicate navigation blocks (filter out)
    nav_markers: list[str] = Field(
        default_factory=lambda: [
            "On This Page",
            "Table of Contents",
            "Related Articles",
            "Share This",
        ]
    )

    # Whether to skip content until first heading
    skip_until_heading: bool = True


class SitemapConfigModel(BaseModel):
    """Configuration for sitemap-based URL discovery.

    Controls whether and how sitemaps are used during crawling.
    """

    model_config = ConfigDict(extra="forbid")

    # Whether to use sitemap discovery
    enabled: bool = False

    # Explicit sitemap URLs to use (overrides auto-discovery)
    urls: list[str] = Field(default_factory=list)

    # If True, only crawl URLs from sitemaps (no link following)
    only: bool = False

    # Only include URLs modified after this date (ISO format string)
    filter_by_lastmod: str | None = None


class RobotsConfigModel(BaseModel):
    """Configuration for robots.txt compliance.

    Controls how the scraper respects robots.txt directives.
    """

    model_config = ConfigDict(extra="forbid")

    # Whether to respect robots.txt at all
    respect: bool = True

    # Enforcement level: strict (block), warn (log only), ignore
    enforcement: str = "warn"

    # User agent for robots.txt matching
    user_agent: str = "WebScraperBot/1.0"

    # Minimum delay between requests (seconds), applied on top of Crawl-delay
    min_delay: float = 0.0


class RateLimitConfigModel(BaseModel):
    """Configuration for rate limiting and politeness controls.

    Controls request pacing to avoid overwhelming target servers.
    """

    model_config = ConfigDict(extra="forbid")

    # Maximum requests per second (global)
    requests_per_second: float = 2.0

    # Minimum seconds between requests to same domain
    per_domain_delay: float = 1.0

    # Maximum concurrent requests
    max_concurrent: int = 5

    # Whether to respect robots.txt Crawl-delay
    respect_crawl_delay: bool = True

    # Whether to adaptively slow down on 429 responses
    adaptive: bool = True


class BrowserPoolConfigModel(BaseModel):
    """Configuration for browser pooling.

    Controls browser reuse and pooling for performance.
    """

    model_config = ConfigDict(extra="forbid")

    # Whether browser pooling is enabled
    enabled: bool = True

    # Number of browsers to maintain in pool
    pool_size: int = 3

    # Maximum pages before recycling a browser
    max_pages_per_browser: int = 100

    # Whether to restart crashed browsers
    restart_on_crash: bool = True


class ProxyConfigModel(BaseModel):
    """Configuration for proxy rotation.

    Controls proxy usage and rotation for avoiding blocks.
    """

    model_config = ConfigDict(extra="forbid")

    # Whether proxy rotation is enabled
    enabled: bool = False

    # Rotation strategy: round_robin, random, health_based
    rotation: str = "round_robin"

    # List of proxy URLs (http://host:port or with auth)
    proxies: list[str] = Field(default_factory=list)

    # Minimum success rate before removing proxy
    min_success_rate: float = 0.5

    # Whether to fall back to direct connection if all proxies fail
    fallback_direct: bool = True


class LinkDiscoveryWorkaroundConfigModel(BaseModel):
    """
    Configuration for link discovery workaround.

    WORKAROUND: This is a temporary workaround where Crawl4AI's deep crawl
    strategies discover links but don't follow them, even with correct filter
    configuration. Issue #1176 is closed but may not have fixed this behavior.
    See: https://github.com/unclecode/crawl4ai/issues/1176

    Test with enabled: false to verify if Crawl4AI deep crawl works correctly.
    This can be removed when Crawl4AI deep crawl correctly follows links.
    """

    model_config = ConfigDict(extra="forbid")

    # Whether to enable the link discovery workaround
    enabled: bool = False

    # Maximum iterations to prevent infinite loops
    max_iterations: int = 10


class MarkdownFixesConfigModel(BaseModel):
    """
    Configuration for markdown fix plugins.

    Markdown fixes are workarounds for issues in upstream tools (like Crawl4AI)
    that miss certain patterns. Each fix can be enabled/disabled individually.

    Configure via site YAML file. Default: disabled (must be explicitly enabled).
    """

    model_config = ConfigDict(extra="forbid")

    # Whether to enable all markdown fixes (default: false)
    enabled: bool = False

    # Per-fix configuration (fix name -> enabled)
    # Example: {"missing-link-text-in-lists": true}
    fixes: dict[str, bool] = Field(default_factory=dict)


class SiteConfig(BaseModel):
    """Model representing a site configuration."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    entrypoints: list[str]
    include: list[str]
    exclude: list[str]
    max_pages: int
    formats: list[str]
    only_main_content: bool
    include_subdomains: bool
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    sitemap: SitemapConfigModel = Field(default_factory=SitemapConfigModel)
    robots: RobotsConfigModel = Field(default_factory=RobotsConfigModel)
    rate_limit: RateLimitConfigModel = Field(default_factory=RateLimitConfigModel)
    browser_pool: BrowserPoolConfigModel = Field(default_factory=BrowserPoolConfigModel)
    proxy: ProxyConfigModel = Field(default_factory=ProxyConfigModel)
    link_discovery_workaround: LinkDiscoveryWorkaroundConfigModel = Field(
        default_factory=LinkDiscoveryWorkaroundConfigModel
    )
    markdown_fixes: MarkdownFixesConfigModel = Field(
        default_factory=MarkdownFixesConfigModel
    )

    @field_validator("entrypoints")
    @classmethod
    def validate_entrypoints(cls, value: list[str]) -> list[str]:
        """
        Ensure at least one entrypoint is provided.

        Args:
            value: List of entrypoint URLs to validate.

        Returns:
            Validated list of entrypoints.

        Raises:
            ValidationError: If the entrypoints list is empty.
        """
        if not value:
            correlation_id = generate_correlation_id()
            raise ValidationError(
                "At least one entrypoint is required. Provide at least one URL in the entrypoints list.",
                field="entrypoints",
                value=value,
                correlation_id=correlation_id,
                context={"example": "entrypoints: ['https://example.com']"},
            )
        return value

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, value: int) -> int:
        """
        Ensure max_pages is positive.

        Args:
            value: Maximum pages value to validate.

        Returns:
            Validated max_pages value.

        Raises:
            ValidationError: If max_pages is zero or negative.
        """
        if value <= 0:
            correlation_id = generate_correlation_id()
            raise ValidationError(
                f"max_pages must be greater than zero, got {value}. Use a positive integer (e.g., 10, 50, 100).",
                field="max_pages",
                value=value,
                correlation_id=correlation_id,
                context={"example": "max_pages: 50"},
            )
        return value

    @field_validator("formats")
    @classmethod
    def validate_formats(cls, value: list[str]) -> list[str]:
        """
        Validate format values are supported.

        Args:
            value: List of format strings.

        Returns:
            Validated list of formats.

        Raises:
            ValidationError: If any format is invalid.
        """
        valid_formats = {f.value for f in OutputFormat}
        aliases = {"md": "markdown", "htm": "html", "txt": "text"}

        normalized: list[str] = []
        for fmt in value:
            fmt_lower = fmt.lower().strip()
            if fmt_lower in aliases:
                fmt_lower = aliases[fmt_lower]
            if fmt_lower not in valid_formats:
                correlation_id = generate_correlation_id()
                raise ValidationError(
                    f"Invalid format '{fmt}'. Supported formats: {', '.join(valid_formats)}.",
                    field="formats",
                    value=value,
                    correlation_id=correlation_id,
                    context={"valid_formats": list(valid_formats)},
                )
            normalized.append(fmt_lower)

        if not normalized:
            normalized = ["markdown"]  # Default to markdown

        return normalized


class Page(BaseModel):
    """Model representing a scraped page."""

    model_config = ConfigDict(extra="forbid")

    site_id: str
    url: str
    title: str
    path: str
    content_markdown: str
    content_html: str | None = None
    content_text: str | None = None
    scraped_at: datetime = Field(default_factory=_brisbane_now)
    content_hash: str
    provider: str
    extra: dict[str, Any] = Field(default_factory=dict)

    def get_text_content(self) -> str:
        """Get plain text content, generating from markdown if needed."""
        if self.content_text:
            return self.content_text
        # Strip markdown formatting for plain text
        import re
        text = self.content_markdown
        # Remove headers
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        # Remove bold/italic
        text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
        # Remove links, keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove images
        text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
        # Remove code blocks
        text = re.sub(r"```[^`]*```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
