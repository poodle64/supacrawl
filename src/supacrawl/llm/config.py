"""LLM configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from supacrawl.exceptions import ConfigurationError, generate_correlation_id

LLMProvider = Literal["ollama", "openai", "anthropic"]

DEFAULT_BASE_URLS: dict[LLMProvider, str] = {
    "ollama": "http://localhost:11434",
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
}


class LLMNotConfiguredError(ConfigurationError):
    """Raised when LLM features are used without proper configuration."""

    def __init__(self, correlation_id: str | None = None) -> None:
        """
        Initialise with helpful configuration guidance.

        Args:
            correlation_id: Optional correlation ID for tracing.
        """
        message = """LLM not configured. Set these environment variables:
  LLM_PROVIDER=ollama|openai|anthropic
  LLM_MODEL=<model-name>

For Ollama (local):
  LLM_PROVIDER=ollama
  LLM_MODEL=qwen3:8b
  LLM_BASE_URL=http://localhost:11434  (optional, this is the default)

For OpenAI:
  LLM_PROVIDER=openai
  LLM_MODEL=gpt-4o-mini
  LLM_API_KEY=sk-...

For Anthropic:
  LLM_PROVIDER=anthropic
  LLM_MODEL=claude-sonnet-4-20250514
  LLM_API_KEY=sk-ant-..."""
        super().__init__(message, correlation_id=correlation_id)


@dataclass(frozen=True)
class LLMConfig:
    """Immutable LLM configuration."""

    provider: LLMProvider
    model: str
    base_url: str
    api_key: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialisation."""
        if self.provider in ("openai", "anthropic") and not self.api_key:
            correlation_id = generate_correlation_id()
            raise ConfigurationError(
                f"LLM_API_KEY is required for {self.provider} provider",
                correlation_id=correlation_id,
                context={"provider": self.provider},
            )


def load_llm_config() -> LLMConfig:
    """
    Load LLM configuration from environment variables.

    Returns:
        LLMConfig with validated settings.

    Raises:
        LLMNotConfiguredError: If required environment variables are not set.
        ConfigurationError: If configuration is invalid.
    """
    correlation_id = generate_correlation_id()

    provider_str = os.getenv("LLM_PROVIDER")
    model = os.getenv("LLM_MODEL")

    if not provider_str or not model:
        raise LLMNotConfiguredError(correlation_id=correlation_id)

    provider_str = provider_str.lower()
    if provider_str not in ("ollama", "openai", "anthropic"):
        raise ConfigurationError(
            f"Invalid LLM_PROVIDER: {provider_str}. Must be one of: ollama, openai, anthropic",
            correlation_id=correlation_id,
            context={"provider": provider_str},
        )

    provider: LLMProvider = provider_str  # type: ignore[assignment]

    base_url = os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URLS[provider]
    api_key = os.getenv("LLM_API_KEY")

    return LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )


def is_llm_configured() -> bool:
    """
    Check if LLM is configured without raising an error.

    Returns:
        True if LLM configuration is valid, False otherwise.
    """
    try:
        load_llm_config()
        return True
    except (LLMNotConfiguredError, ConfigurationError):
        return False
