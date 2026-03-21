"""Request and response models for the POST /scrape endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ScrapeRequest(BaseModel):
    """Firecrawl v2-compatible scrape request body.

    Accepts camelCase field names (v2 protocol) and silently ignores
    fields that Supacrawl does not support.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        extra="ignore",
    )

    url: str
    formats: list[str] | None = None
    only_main_content: bool = True
    wait_for: int = 0
    timeout: int = 30000
    include_tags: list[str] | None = None
    exclude_tags: list[str] | None = None
    mobile: bool | None = None
    actions: list[Any] | None = None
    location: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    max_age: int | None = Field(None, alias="maxAge")
    proxy: str | bool | None = None
    store_in_cache: bool | None = Field(None, alias="storeInCache")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class ScrapeMetadataResponse(BaseModel):
    """Metadata portion of the scrape response (camelCase output)."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        serialize_by_alias=True,
    )

    title: str | None = None
    description: str | None = None
    source_url: str | None = Field(None, serialization_alias="sourceURL")
    url: str | None = None
    status_code: int | None = None
    language: str | None = None


class ScrapeDataResponse(BaseModel):
    """Data envelope for a single scrape result (camelCase output)."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        serialize_by_alias=True,
    )

    markdown: str | None = None
    html: str | None = None
    raw_html: str | None = Field(None, serialization_alias="rawHtml")
    links: list[str] | None = None
    screenshot: str | None = None
    metadata: ScrapeMetadataResponse
    actions: dict[str, Any] | None = None
    branding: dict[str, Any] | None = None
    change_tracking: dict[str, Any] | None = None


class ScrapeResponse(BaseModel):
    """Top-level scrape response envelope."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        serialize_by_alias=True,
    )

    success: bool
    data: ScrapeDataResponse | None = None
    error: str | None = None
