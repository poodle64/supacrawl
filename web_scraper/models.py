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
    def from_string(cls, value: str) -> OutputFormat:
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


class CrawlPolitenessConfig(BaseModel):
    """Configuration for crawl politeness and pacing.

    These settings map directly to Crawl4AI's native controls.
    All timing values are in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    # Maximum concurrent page crawls (Crawl4AI SemaphoreDispatcher.max_session_permit)
    max_concurrent: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent page crawls (1-20)",
    )

    # Delay between requests in seconds (min, max) for random jitter
    # Maps to Crawl4AI RateLimiter.base_delay
    delay_between_requests: tuple[float, float] = Field(
        default=(1.0, 2.0),
        description="Delay range (min, max) seconds between requests",
    )

    # Page timeout in seconds (Crawl4AI page_timeout, converted to ms internally)
    page_timeout: float = Field(
        default=120.0,
        ge=5.0,
        le=600.0,
        description="Maximum time to wait for a page to load (seconds)",
    )

    # Maximum retry attempts for failed requests
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed requests",
    )


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

    # id is auto-derived from filename if not provided
    # The validator ensures it's always a string after validation
    id: str | None = None
    name: str
    entrypoints: list[str]
    include: list[str]
    exclude: list[str]
    max_pages: int
    formats: list[str]
    only_main_content: bool
    include_subdomains: bool
    sitemap: SitemapConfigModel = Field(default_factory=SitemapConfigModel)
    robots: RobotsConfigModel = Field(default_factory=RobotsConfigModel)
    politeness: CrawlPolitenessConfig = Field(default_factory=CrawlPolitenessConfig)
    markdown_fixes: MarkdownFixesConfigModel = Field(
        default_factory=MarkdownFixesConfigModel
    )

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization to derive or validate id."""
        # Get expected_id from context (set by loader)
        expected_id = __context.get("expected_id") if __context else None

        # If id is missing or None, derive it from expected_id
        if self.id is None:
            if expected_id is None:
                correlation_id = generate_correlation_id()
                raise ValidationError(
                    "Site configuration must have an 'id' field or be loaded with filename context.",
                    field="id",
                    value=self.id,
                    correlation_id=correlation_id,
                    context={"expected_id": expected_id},
                )
            # Auto-derive from filename stem
            object.__setattr__(self, "id", expected_id)
        elif expected_id is not None and self.id != expected_id:
            # If id is present, validate it matches the filename stem
            correlation_id = generate_correlation_id()
            raise ValidationError(
                f"Site configuration 'id' field ('{self.id}') must match the filename stem ('{expected_id}'). "
                f"Either remove the 'id' field to auto-derive it, or set it to '{expected_id}'.",
                field="id",
                value=self.id,
                correlation_id=correlation_id,
                context={"expected_id": expected_id, "actual_id": self.id},
            )

        # After post_init, id is guaranteed to be a string (for type checkers)
        assert self.id is not None, "id must be set after validation"

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


class MapLink(BaseModel):
    """A discovered URL with metadata (Firecrawl-compatible)."""

    url: str
    title: str | None = None
    description: str | None = None


class MapResult(BaseModel):
    """Result of a map operation (Firecrawl-compatible)."""

    success: bool
    links: list[MapLink]
    error: str | None = None


class ScrapeMetadata(BaseModel):
    """Metadata extracted from a page (Firecrawl-compatible)."""

    title: str | None = None
    description: str | None = None
    language: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    og_image: str | None = None
    source_url: str | None = None
    status_code: int | None = None


class ScrapeData(BaseModel):
    """Scraped content from a page (Firecrawl-compatible)."""

    markdown: str | None = None
    html: str | None = None
    raw_html: str | None = None
    metadata: ScrapeMetadata
    links: list[str] | None = None


class ScrapeResult(BaseModel):
    """Result of a scrape operation (Firecrawl-compatible)."""

    success: bool
    data: ScrapeData | None = None
    error: str | None = None
