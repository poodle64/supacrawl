"""Ollama client utilities for LLM processing."""

from __future__ import annotations

import logging
import os

from ollama import AsyncClient  # type: ignore[import-untyped]

from web_scraper.exceptions import ProviderError, generate_correlation_id
from web_scraper.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


class OllamaClient:
    """Client for interacting with Ollama API."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """
        Initialise Ollama client.

        Args:
            host: Ollama server URL. Defaults to http://localhost:11434.
            model: Default model to use. Can be overridden per request.
            timeout: Request timeout in seconds.
        """
        self._host: str = host or os.getenv("OLLAMA_HOST") or "http://localhost:11434"
        self._model: str = model or os.getenv("OLLAMA_MODEL") or "llama3.2"
        self._timeout: float = timeout
        self._client = AsyncClient(host=self._host, timeout=self._timeout)

    async def summarize(
        self, text: str, model: str | None = None, max_length: int | None = None
    ) -> str:
        """
        Summarize text content using Ollama.

        Args:
            text: Text content to summarize.
            model: Model to use. Defaults to client default model.
            max_length: Optional maximum length for summary.

        Returns:
            Summarized text.

        Raises:
            ProviderError: If Ollama request fails.
        """
        correlation_id = generate_correlation_id()
        model_name: str = model or self._model

        prompt = "Summarize the following text concisely, preserving key information:\n\n"
        if max_length:
            prompt += f"Keep the summary under {max_length} words.\n\n"
        prompt += text

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Requesting Ollama summarization",
                correlation_id=correlation_id,
                model=model_name,
                text_length=len(text),
            )
            response = await self._client.generate(
                model=model_name,
                prompt=prompt,
            )
            summary = response.get("response", "").strip()
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Ollama summarization completed",
                correlation_id=correlation_id,
                model=model_name,
                summary_length=len(summary),
            )
            return summary
        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.ERROR,
                f"Ollama summarization failed: {exc}",
                correlation_id=correlation_id,
                model=model_name,
                error=str(exc),
                error_type=str(type(exc)),
            )
            raise ProviderError(
                f"Ollama summarization failed: {str(exc)}",
                provider="ollama",
                correlation_id=correlation_id,
                context={"model": model_name, "error": str(exc)},
            ) from exc

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str:
        """
        Send chat messages to Ollama.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model to use. Defaults to client default model.

        Returns:
            Assistant's response content.

        Raises:
            ProviderError: If Ollama request fails.
        """
        correlation_id = generate_correlation_id()
        model_name: str = model or self._model

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Sending chat request to Ollama",
                correlation_id=correlation_id,
                model=model_name,
                message_count=len(messages),
            )
            response = await self._client.chat(model=model_name, messages=messages)
            content = (response.message.content or "").strip()
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Ollama chat completed",
                correlation_id=correlation_id,
                model=model_name,
                response_length=len(content),
            )
            return content
        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.ERROR,
                f"Ollama chat failed: {exc}",
                correlation_id=correlation_id,
                model=model_name,
                error=str(exc),
                error_type=str(type(exc)),
            )
            raise ProviderError(
                f"Ollama chat failed: {str(exc)}",
                provider="ollama",
                correlation_id=correlation_id,
                context={"model": model_name, "error": str(exc)},
            ) from exc

    async def check_health(self) -> bool:
        """
        Check if Ollama server is accessible.

        Returns:
            True if Ollama is accessible, False otherwise.
        """
        try:
            # Try to list models as a health check
            response = await self._client.list()
            # Response should be a dict with 'models' key
            return isinstance(response, dict) and "models" in response
        except Exception:
            return False
