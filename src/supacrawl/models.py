"""Data models for supacrawl."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from supacrawl.exceptions import ValidationError, generate_correlation_id


# =============================================================================
# Locale/Location Configuration
# =============================================================================

# Default country-to-locale mappings
COUNTRY_DEFAULTS: dict[str, tuple[str, str]] = {
    "AU": ("en-AU", "Australia/Sydney"),
    "US": ("en-US", "America/New_York"),
    "GB": ("en-GB", "Europe/London"),
    "DE": ("de-DE", "Europe/Berlin"),
    "FR": ("fr-FR", "Europe/Paris"),
    "JP": ("ja-JP", "Asia/Tokyo"),
    "CN": ("zh-CN", "Asia/Shanghai"),
    "IN": ("en-IN", "Asia/Kolkata"),
    "BR": ("pt-BR", "America/Sao_Paulo"),
    "CA": ("en-CA", "America/Toronto"),
    "NZ": ("en-NZ", "Pacific/Auckland"),
    "SG": ("en-SG", "Asia/Singapore"),
    "HK": ("zh-HK", "Asia/Hong_Kong"),
    "KR": ("ko-KR", "Asia/Seoul"),
    "ES": ("es-ES", "Europe/Madrid"),
    "IT": ("it-IT", "Europe/Rome"),
    "NL": ("nl-NL", "Europe/Amsterdam"),
    "SE": ("sv-SE", "Europe/Stockholm"),
    "CH": ("de-CH", "Europe/Zurich"),
    "AT": ("de-AT", "Europe/Vienna"),
    "BE": ("nl-BE", "Europe/Brussels"),
    "PL": ("pl-PL", "Europe/Warsaw"),
    "RU": ("ru-RU", "Europe/Moscow"),
    "MX": ("es-MX", "America/Mexico_City"),
    "AR": ("es-AR", "America/Buenos_Aires"),
}


class LocaleConfig(BaseModel):
    """Configuration for browser locale and timezone.

    Used to simulate requests from different geographic regions. As a local-first
    tool, Supacrawl sets browser locale/timezone and Accept-Language headers.
    For true geo-targeting, users should configure their own proxy.

    Usage:
        # From country code (uses sensible defaults)
        config = LocaleConfig.from_country("AU")

        # Explicit configuration
        config = LocaleConfig(language="en-AU", timezone="Australia/Sydney")
    """

    model_config = ConfigDict(extra="forbid")

    # ISO country code (e.g., "AU", "US", "DE")
    country: str | None = None

    # Language/locale code (e.g., "en-AU", "de-DE")
    language: str | None = None

    # IANA timezone (e.g., "Australia/Sydney", "Europe/Berlin")
    timezone: str | None = None

    @classmethod
    def from_country(cls, country: str) -> "LocaleConfig":
        """Create config with sensible defaults for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code (e.g., "AU", "US", "DE")

        Returns:
            LocaleConfig with language and timezone defaults for the country.
        """
        country_upper = country.upper()
        lang, tz = COUNTRY_DEFAULTS.get(country_upper, ("en-US", "UTC"))
        return cls(country=country_upper, language=lang, timezone=tz)

    def get_language(self) -> str:
        """Get effective language, with fallback to en-US."""
        return self.language or "en-US"

    def get_timezone(self) -> str:
        """Get effective timezone, with fallback to UTC."""
        return self.timezone or "UTC"

    def get_accept_language_header(self) -> str:
        """Build Accept-Language header value.

        Returns:
            Accept-Language header string (e.g., "en-AU,en;q=0.9")
        """
        lang = self.get_language()
        # Extract base language (e.g., "en" from "en-AU")
        base_lang = lang.split("-")[0]
        if base_lang != lang:
            return f"{lang},{base_lang};q=0.9"
        return lang


# =============================================================================
# Output Formats
# =============================================================================


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
    user_agent: str = "SupacrawlBot/1.0"

    # Minimum delay between requests (seconds), applied on top of Crawl-delay
    min_delay: float = 0.0


class CrawlPolitenessConfig(BaseModel):
    """Configuration for crawl politeness and pacing.

    These settings control browser automation and request pacing.
    All timing values are in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    # Maximum concurrent page crawls
    max_concurrent: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent page crawls (1-20)",
    )

    # Delay between requests in seconds (min, max) for random jitter
    delay_between_requests: tuple[float, float] = Field(
        default=(1.0, 2.0),
        description="Delay range (min, max) seconds between requests",
    )

    # Page timeout in seconds
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
    """Metadata extracted from a page (Firecrawl-compatible).

    Fields match Firecrawl's metadata response format for compatibility.
    See: https://docs.firecrawl.dev/features/scrape
    """

    # Core metadata
    title: str | None = None
    description: str | None = None
    language: str | None = None
    keywords: str | None = None
    robots: str | None = None
    canonical_url: str | None = None

    # OpenGraph metadata
    og_title: str | None = None
    og_description: str | None = None
    og_image: str | None = None
    og_url: str | None = None
    og_site_name: str | None = None

    # Source information
    source_url: str | None = None
    status_code: int | None = None

    # Content metrics (computed)
    word_count: int | None = None

    # Cache metadata (Firecrawl-compatible)
    cache_hit: bool = False
    cached_at: str | None = None

    def to_frontmatter(
        self,
        url: str | None = None,
        *,
        site_id: str | None = None,
        snapshot_id: str | None = None,
        content_hash: str | None = None,
        provider: str | None = None,
        scraped_at: datetime | None = None,
    ) -> str:
        """Build YAML frontmatter from metadata.

        Args:
            url: URL to use (defaults to source_url if not provided)
            site_id: Site identifier (for corpus output)
            snapshot_id: Snapshot identifier (for corpus output)
            content_hash: Content hash (for corpus output)
            provider: Scraping provider (for corpus output)
            scraped_at: Timestamp to use (defaults to now if not provided)

        Returns:
            YAML frontmatter string including opening and closing delimiters.
        """
        from datetime import timezone

        def escape_yaml(s: str | None) -> str:
            """Escape string for YAML double-quoted value."""
            if not s:
                return ""
            return s.replace("\\", "\\\\").replace('"', '\\"')

        source = url or self.source_url or ""
        timestamp = scraped_at or datetime.now(timezone.utc)
        lines = [
            "---",
            f'url: "{escape_yaml(source)}"',
            f'title: "{escape_yaml(self.title)}"',
            f"scraped_at: {timestamp.isoformat()}",
        ]

        # Add corpus fields if provided
        if content_hash:
            lines.append(f"content_hash: sha256:{content_hash}")
        if site_id:
            lines.append(f"site_id: {site_id}")
        if snapshot_id:
            lines.append(f"snapshot_id: {snapshot_id}")
        if provider:
            lines.append(f"provider: {provider}")

        # Add optional core metadata
        if self.description:
            lines.append(f'description: "{escape_yaml(self.description)}"')
        if self.language:
            lines.append(f"language: {self.language}")
        if self.keywords:
            lines.append(f'keywords: "{escape_yaml(self.keywords)}"')
        if self.robots:
            lines.append(f"robots: {self.robots}")
        if self.canonical_url:
            lines.append(f'canonical_url: "{self.canonical_url}"')
        if self.status_code:
            lines.append(f"status_code: {self.status_code}")

        # Add OpenGraph metadata
        if self.og_title:
            lines.append(f'og_title: "{escape_yaml(self.og_title)}"')
        if self.og_description:
            lines.append(f'og_description: "{escape_yaml(self.og_description)}"')
        if self.og_image:
            lines.append(f'og_image: "{self.og_image}"')
        if self.og_url:
            lines.append(f'og_url: "{self.og_url}"')
        if self.og_site_name:
            lines.append(f'og_site_name: "{escape_yaml(self.og_site_name)}"')

        # Add content metrics
        if self.word_count:
            lines.append(f"word_count: {self.word_count}")

        lines.append("---")
        return "\n".join(lines)


class BrandingColors(BaseModel):
    """Brand colour palette (Firecrawl-compatible)."""

    primary: str | None = None
    secondary: str | None = None
    accent: str | None = None
    background: str | None = None
    text_primary: str | None = None
    text_secondary: str | None = None


class BrandingProfile(BaseModel):
    """Brand identity information extracted from page (Firecrawl-compatible)."""

    color_scheme: Literal["light", "dark"] | None = None
    logo: str | None = None
    colors: BrandingColors | None = None
    fonts: list[dict[str, str]] | None = None
    typography: dict[str, Any] | None = None
    spacing: dict[str, Any] | None = None
    components: dict[str, Any] | None = None
    images: dict[str, str] | None = None


class ScrapeActionResult(BaseModel):
    """Result of a mid-workflow scrape action (Firecrawl-compatible).

    Captures page content at a specific point during an action sequence.
    """

    url: str
    html: str
    markdown: str | None = None


class ActionsOutput(BaseModel):
    """Output from page actions (Firecrawl-compatible).

    Contains results from screenshot and scrape actions executed during
    a scrape workflow.
    """

    screenshots: list[str] | None = None  # Base64-encoded screenshots
    scrapes: list[ScrapeActionResult] | None = None  # Mid-workflow scrape captures


class ScrapeData(BaseModel):
    """Scraped content from a page (Firecrawl-compatible)."""

    markdown: str | None = None
    html: str | None = None
    raw_html: str | None = None
    screenshot: str | None = None  # Base64-encoded PNG screenshot
    pdf: str | None = None  # Base64-encoded PDF document
    llm_extraction: dict[str, Any] | None = Field(None, alias="json")  # LLM-extracted structured data (Firecrawl uses "json" key)
    summary: str | None = None  # LLM-generated summary of page content
    metadata: ScrapeMetadata
    links: list[str] | None = None
    images: list[str] | None = None  # Image URLs extracted from page
    branding: BrandingProfile | None = None  # Brand identity information
    actions: ActionsOutput | None = None  # Results from action sequence

    model_config = ConfigDict(populate_by_name=True)


class ScrapeResult(BaseModel):
    """Result of a scrape operation (Firecrawl-compatible)."""

    success: bool
    data: ScrapeData | None = None
    error: str | None = None


class CrawlEvent(BaseModel):
    """Event emitted during crawl (Firecrawl-compatible)."""

    type: Literal["progress", "page", "complete", "error"]
    url: str | None = None
    data: ScrapeData | None = None
    completed: int = 0
    total: int = 0
    error: str | None = None


class BatchItem(BaseModel):
    """Result for a single URL in a batch (Firecrawl-compatible)."""

    url: str
    success: bool
    data: ScrapeData | None = None
    error: str | None = None


class BatchEvent(BaseModel):
    """Event emitted during batch processing (Firecrawl-compatible)."""

    type: Literal["progress", "item", "complete"]
    url: str | None = None
    item: BatchItem | None = None
    completed: int = 0
    total: int = 0


class BatchResult(BaseModel):
    """Final result of a batch operation (Firecrawl-compatible)."""

    success: bool
    completed: int
    total: int
    successful: int
    failed: int
    data: list[BatchItem]


# =============================================================================
# Search Models (Firecrawl-compatible)
# =============================================================================


class SearchSourceType(str, Enum):
    """Search source types (Firecrawl-compatible)."""

    WEB = "web"
    IMAGES = "images"
    NEWS = "news"


class SearchResultItem(BaseModel):
    """Individual search result (Firecrawl-compatible)."""

    url: str
    title: str
    description: str | None = None
    source_type: SearchSourceType = SearchSourceType.WEB

    # Image-specific fields
    thumbnail: str | None = None
    image_width: int | None = None
    image_height: int | None = None

    # News-specific fields
    published_at: str | None = None
    source_name: str | None = None

    # Scraped content (if scrape_options provided)
    markdown: str | None = None
    html: str | None = None
    metadata: ScrapeMetadata | None = None


class SearchResult(BaseModel):
    """Search operation result (Firecrawl-compatible)."""

    success: bool
    data: list[SearchResultItem]
    error: str | None = None


# =============================================================================
# Extract Models (Firecrawl-compatible)
# =============================================================================


class ExtractResultItem(BaseModel):
    """Extraction result for a single URL (Firecrawl-compatible)."""

    url: str
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


class ExtractResult(BaseModel):
    """Overall extraction result (Firecrawl-compatible)."""

    success: bool
    data: list[ExtractResultItem]
    error: str | None = None


# =============================================================================
# Agent Models (Firecrawl-compatible)
# =============================================================================


class AgentEvent(BaseModel):
    """Event emitted during agent execution (Firecrawl-compatible)."""

    type: Literal["thinking", "action", "result", "complete", "error"]
    message: str | None = None
    url: str | None = None
    data: dict[str, Any] | None = None


class AgentResult(BaseModel):
    """Final agent result (Firecrawl-compatible)."""

    success: bool
    data: dict[str, Any] | None = None
    urls_visited: list[str] = Field(default_factory=list)
    error: str | None = None
