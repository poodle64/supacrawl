"""Unified LLM client supporting multiple providers."""

import json
import logging
from typing import Any

import httpx

from supacrawl.exceptions import ProviderError, generate_correlation_id
from supacrawl.llm.config import LLMConfig
from supacrawl.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


class LLMClient:
    """
    Unified async LLM client that abstracts provider differences.

    Usage:
        from supacrawl.llm import LLMClient, load_llm_config

        config = load_llm_config()
        client = LLMClient(config)

        response = await client.chat([
            {"role": "user", "content": "Hello!"}
        ])
        await client.close()
    """

    def __init__(self, config: LLMConfig, timeout: float = 120.0) -> None:
        """
        Initialise LLM client.

        Args:
            config: LLM configuration.
            timeout: Request timeout in seconds.
        """
        self._config = config
        self._timeout = timeout
        self._http_client: httpx.AsyncClient | None = None
        self._ollama_client: Any | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for cloud providers."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client

    async def _get_ollama_client(self) -> Any:
        """Get or create Ollama AsyncClient."""
        if self._ollama_client is None:
            from ollama import AsyncClient  # type: ignore[import-untyped]

            self._ollama_client = AsyncClient(
                host=self._config.base_url,
                timeout=self._timeout,
            )
        return self._ollama_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        """
        Send chat messages and return response content.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            json_mode: If True, request JSON formatted output.

        Returns:
            Assistant's response content.

        Raises:
            ProviderError: If the request fails.
        """
        if self._config.provider == "ollama":
            return await self._chat_ollama(messages, json_mode)
        elif self._config.provider == "openai":
            return await self._chat_openai(messages, json_mode)
        elif self._config.provider == "anthropic":
            return await self._chat_anthropic(messages, json_mode)
        else:
            raise ProviderError(
                f"Unsupported provider: {self._config.provider}",
                provider=self._config.provider,
            )

    async def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """
        Send chat messages and parse JSON response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            ProviderError: If request or JSON parsing fails.
        """
        correlation_id = generate_correlation_id()
        content = await self.chat(messages, json_mode=True)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            parsed = self._extract_json(content)
            if parsed is not None:
                return parsed

            log_with_correlation(
                LOGGER,
                logging.ERROR,
                "Failed to parse JSON response",
                correlation_id=correlation_id,
                content_preview=content[:200],
            )
            raise ProviderError(
                f"Failed to parse JSON from LLM response: {content[:200]}...",
                provider=self._config.provider,
                correlation_id=correlation_id,
                context={"content_preview": content[:200]},
            ) from None

    async def summarize(self, text: str, max_length: int | None = None) -> str:
        """
        Summarize text content.

        Args:
            text: Text content to summarize.
            max_length: Optional maximum length for summary in words.

        Returns:
            Summarized text.

        Raises:
            ProviderError: If request fails.
        """
        prompt = "Summarize the following text concisely, preserving key information:\n\n"
        if max_length:
            prompt += f"Keep the summary under {max_length} words.\n\n"
        prompt += text

        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages)

    async def check_health(self) -> bool:
        """
        Check if the LLM provider is accessible.

        Returns:
            True if provider is accessible, False otherwise.
        """
        try:
            if self._config.provider == "ollama":
                client = await self._get_ollama_client()
                response = await client.list()
                return isinstance(response, dict) and "models" in response
            elif self._config.provider == "openai":
                client = await self._get_http_client()
                response = await client.get(
                    f"{self._config.base_url}/v1/models",
                    headers={"Authorization": f"Bearer {self._config.api_key}"},
                )
                return response.status_code == 200
            elif self._config.provider == "anthropic":
                # Anthropic doesn't have a simple health check endpoint
                return bool(self._config.api_key)
            return False
        except Exception:
            return False

    async def _chat_ollama(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        """Call Ollama API."""
        correlation_id = generate_correlation_id()
        client = await self._get_ollama_client()

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Sending chat request to Ollama",
                correlation_id=correlation_id,
                model=self._config.model,
                message_count=len(messages),
                json_mode=json_mode,
            )

            kwargs: dict[str, Any] = {"model": self._config.model, "messages": messages}
            if json_mode:
                kwargs["format"] = "json"

            response = await client.chat(**kwargs)
            content = (response.message.content or "").strip()

            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Ollama chat completed",
                correlation_id=correlation_id,
                model=self._config.model,
                response_length=len(content),
            )
            return content

        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.ERROR,
                f"Ollama chat failed: {exc}",
                correlation_id=correlation_id,
                model=self._config.model,
                error=str(exc),
            )
            raise ProviderError(
                f"Ollama chat failed: {str(exc)}",
                provider="ollama",
                correlation_id=correlation_id,
                context={"model": self._config.model, "error": str(exc)},
            ) from exc

    async def _chat_openai(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        """Call OpenAI API."""
        correlation_id = generate_correlation_id()
        client = await self._get_http_client()

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Calling OpenAI API",
                correlation_id=correlation_id,
                model=self._config.model,
            )

            request_body: dict[str, Any] = {
                "model": self._config.model,
                "messages": messages,
            }
            if json_mode:
                request_body["response_format"] = {"type": "json_object"}

            response = await client.post(
                f"{self._config.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._config.api_key}"},
                json=request_body,
            )
            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"OpenAI API error: {exc.response.status_code}",
                provider="openai",
                correlation_id=correlation_id,
                context={"status_code": exc.response.status_code},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                f"OpenAI request failed: {str(exc)}",
                provider="openai",
                correlation_id=correlation_id,
            ) from exc

    async def _chat_anthropic(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        """Call Anthropic API."""
        correlation_id = generate_correlation_id()
        client = await self._get_http_client()

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                "Calling Anthropic API",
                correlation_id=correlation_id,
                model=self._config.model,
            )

            # Anthropic uses system message differently
            system_content = None
            api_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                else:
                    api_messages.append(msg)

            request_body: dict[str, Any] = {
                "model": self._config.model,
                "max_tokens": 4096,
                "messages": api_messages,
            }
            if system_content:
                request_body["system"] = system_content

            # api_key is required for Anthropic
            assert self._config.api_key is not None
            response = await client.post(
                f"{self._config.base_url}/v1/messages",
                headers={
                    "x-api-key": self._config.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=request_body,
            )
            response.raise_for_status()

            data = response.json()
            return data["content"][0]["text"].strip()

        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Anthropic API error: {exc.response.status_code}",
                provider="anthropic",
                correlation_id=correlation_id,
                context={"status_code": exc.response.status_code},
            ) from exc
        except Exception as exc:
            raise ProviderError(
                f"Anthropic request failed: {str(exc)}",
                provider="anthropic",
                correlation_id=correlation_id,
            ) from exc

    def _extract_json(self, content: str) -> dict[str, Any] | None:
        """
        Try to extract JSON from content that may contain markdown code blocks.

        Args:
            content: Response content that may contain JSON.

        Returns:
            Parsed dict if found, None otherwise.
        """
        content = content.strip()

        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json code block
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                try:
                    return json.loads(content[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Try extracting from generic ``` code block
        if "```" in content:
            start = content.find("```") + 3
            newline = content.find("\n", start)
            if newline > start:
                start = newline + 1
            end = content.find("```", start)
            if end > start:
                try:
                    return json.loads(content[start:end].strip())
                except json.JSONDecodeError:
                    pass

        return None
