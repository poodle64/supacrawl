"""Data models for supacrawl."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
