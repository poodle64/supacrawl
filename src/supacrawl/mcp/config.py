"""
Configuration for Supacrawl MCP server.

Uses Pydantic Settings for type-safe environment variable loading.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

import supacrawl
from supacrawl.mcp.mcp_common.config import parse_comma_separated
from supacrawl.mcp.mcp_common.logging import setup_server_logging

load_dotenv()


class SupacrawlSettings(BaseSettings):
    """Supacrawl MCP server settings."""

    model_config = ConfigDict(
        env_prefix="SUPACRAWL_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Browser settings
    timeout: int = Field(default=30000, ge=1000, le=300000, description="Page load timeout (ms)")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    user_agent: str | None = Field(default=None, description="Custom user agent string")
    wait_until: str = Field(
        default="domcontentloaded",
        description="Page wait condition: domcontentloaded, load, or networkidle",
    )

    # Anti-bot protection
    stealth: bool = Field(
        default=False,
        description="Enable enhanced stealth mode via Patchright (requires: pip install supacrawl[stealth])",
    )
    proxy: str | None = Field(
        default=None,
        description="Proxy URL (e.g., http://user:pass@host:port, socks5://host:port)",
    )

    # Locale settings (matches upstream supacrawl)
    locale: str = Field(
        default="en-US",
        description="Browser locale (e.g., en-AU, de-DE). Maps to Accept-Language header.",
    )
    timezone: str = Field(
        default="UTC",
        description="Browser timezone (e.g., Australia/Sydney, Europe/Berlin).",
    )

    # Caching
    cache_dir: str | None = Field(
        default=None,
        description="Cache directory for scraped content. Enables max_age caching when set.",
    )

    # CAPTCHA solving
    solve_captcha: bool = Field(
        default=False,
        description="Enable CAPTCHA solving via 2Captcha (requires: pip install supacrawl[captcha])",
    )
    # Note: Uses CAPTCHA_API_KEY and CAPTCHA_TIMEOUT (no prefix) to match upstream supacrawl
    captcha_api_key: str | None = Field(
        default=None,
        alias="CAPTCHA_API_KEY",
        description="2Captcha API key for CAPTCHA solving. WARNING: Each solve costs ~$0.002-0.003",
    )
    captcha_timeout: int = Field(
        default=120,
        ge=30,
        le=600,
        alias="CAPTCHA_TIMEOUT",
        description="CAPTCHA solving timeout in seconds (default: 120)",
    )

    # Search settings (LLM config is read directly from env by supacrawl)
    search_provider: Literal["duckduckgo", "brave"] = Field(
        default="duckduckgo", description="Web search provider (duckduckgo or brave)"
    )

    # MCP Server Configuration (without SUPACRAWL_ prefix)
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        alias="ALLOWED_ORIGINS",
    )
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["*"],
        alias="ALLOWED_HOSTS",
    )
    service_name: str = Field(default="supacrawl-mcp", alias="SERVICE_NAME")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper

    @field_validator("wait_until")
    @classmethod
    def validate_wait_until(cls, v: str) -> str:
        """Ensure wait_until is valid."""
        valid_values = {"domcontentloaded", "load", "networkidle"}
        lower = v.lower()
        if lower not in valid_values:
            raise ValueError(f"Invalid wait_until: {v}. Must be one of {valid_values}")
        return lower

    @field_validator("allowed_origins", "allowed_hosts", mode="before")
    @classmethod
    def validate_comma_separated(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated string into list."""
        return parse_comma_separated(v)

    def get_cache_path(self) -> Path | None:
        """Get cache directory as Path, expanding ~ if present."""
        if self.cache_dir:
            return Path(self.cache_dir).expanduser()
        return None

    def get_locale_config(self):
        """Get LocaleConfig from locale and timezone settings."""
        from supacrawl.models import LocaleConfig

        return LocaleConfig(
            language=self.locale,
            timezone=self.timezone,
        )


@lru_cache
def get_settings() -> SupacrawlSettings:
    """Get cached settings instance."""
    return SupacrawlSettings()


# Create settings instance
settings = get_settings()

# Export module-level constants for explicit imports
ALLOWED_ORIGINS = settings.allowed_origins
ALLOWED_HOSTS = settings.allowed_hosts
SERVICE_NAME = settings.service_name

# Setup logging using mcp-common structured JSON logging
# Version tracks the underlying supacrawl library for debugging clarity
SERVICE_VERSION = supacrawl.__version__

logger = setup_server_logging(SERVICE_NAME, SERVICE_VERSION)
