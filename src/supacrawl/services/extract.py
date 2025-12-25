"""
LLM-powered extraction service for supacrawl.

Extracts structured data from web pages using local or cloud LLMs.
Supports Ollama (default), OpenAI, and Anthropic.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any, Literal

import httpx

from supacrawl.exceptions import ProviderError, generate_correlation_id
from supacrawl.models import ExtractResult, ExtractResultItem
from supacrawl.prep.ollama_client import OllamaClient
from supacrawl.utils import log_with_correlation

if TYPE_CHECKING:
    from supacrawl.services.scrape import ScrapeService

LOGGER = logging.getLogger(__name__)


class ExtractService:
    """
    LLM-powered structured data extraction from web pages.

    Uses local LLMs (Ollama) by default, with fallback to cloud providers.

    Example usage:
        >>> from supacrawl.services.scrape import ScrapeService
        >>> scrape_svc = ScrapeService()
        >>> extract_svc = ExtractService(scrape_service=scrape_svc)
        >>> result = await extract_svc.extract(
        ...     urls=["https://example.com/product"],
        ...     prompt="Extract the product name and price",
        ...     schema={"type": "object", "properties": {"name": {"type": "string"}}}
        ... )
    """

    def __init__(
        self,
        scrape_service: "ScrapeService",
        provider: Literal["ollama", "openai", "anthropic"] = "ollama",
        model: str | None = None,
        ollama_host: str | None = None,
    ):
        """
        Initialise extraction service.

        Args:
            scrape_service: ScrapeService for fetching page content.
            provider: LLM provider ("ollama", "openai", "anthropic").
            model: Model name. Defaults vary by provider.
            ollama_host: Ollama server URL (for ollama provider).
        """
        self._scrape_service = scrape_service
        self._provider = provider
        self._model = model or self._default_model()
        self._ollama_host = ollama_host

        # Clients (lazily initialised)
        self._ollama_client: OllamaClient | None = None
        self._http_client: httpx.AsyncClient | None = None

    def _default_model(self) -> str:
        """Get default model for current provider."""
        defaults = {
            "ollama": os.getenv("OLLAMA_MODEL", "llama3.2"),
            "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
        }
        return defaults.get(self._provider, "llama3.2")

    async def _get_ollama_client(self) -> OllamaClient:
        """Get or create Ollama client."""
        if self._ollama_client is None:
            self._ollama_client = OllamaClient(
                host=self._ollama_host,
                model=self._model,
            )
        return self._ollama_client

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for cloud providers."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=120.0)
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def extract(
        self,
        urls: list[str],
        prompt: str | None = None,
        schema: dict[str, Any] | None = None,
        allow_external_links: bool = False,
    ) -> ExtractResult:
        """
        Extract structured data from URLs using LLM.

        Args:
            urls: URLs to extract data from.
            prompt: Custom extraction prompt.
            schema: JSON schema for structured output.
            allow_external_links: Follow and extract from external links.

        Returns:
            ExtractResult with extracted data for each URL.
        """
        correlation_id = generate_correlation_id()
        results: list[ExtractResultItem] = []

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"Starting extraction for {len(urls)} URLs",
            correlation_id=correlation_id,
            provider=self._provider,
            model=self._model,
        )

        for url in urls:
            try:
                result = await self._extract_single(url, prompt, schema, correlation_id)
                results.append(result)
            except Exception as e:
                log_with_correlation(
                    LOGGER,
                    logging.ERROR,
                    f"Extraction failed for {url}: {e}",
                    correlation_id=correlation_id,
                    error=str(e),
                )
                results.append(
                    ExtractResultItem(url=url, success=False, error=str(e))
                )

        all_success = all(r.success for r in results)

        log_with_correlation(
            LOGGER,
            logging.INFO,
            f"Extraction completed: {sum(1 for r in results if r.success)}/{len(results)} successful",
            correlation_id=correlation_id,
        )

        return ExtractResult(success=all_success, data=results)

    async def _extract_single(
        self,
        url: str,
        prompt: str | None,
        schema: dict[str, Any] | None,
        correlation_id: str,
    ) -> ExtractResultItem:
        """Extract from a single URL."""
        # First, scrape the page content
        scrape_result = await self._scrape_service.scrape(
            url=url,
            formats=["markdown"],
            only_main_content=True,
        )

        if not scrape_result.success or not scrape_result.data:
            return ExtractResultItem(
                url=url,
                success=False,
                error=scrape_result.error or "Failed to scrape page",
            )

        content = scrape_result.data.markdown or ""
        if not content.strip():
            return ExtractResultItem(
                url=url,
                success=False,
                error="No content extracted from page",
            )

        # Build extraction prompt
        system_prompt = self._build_system_prompt(schema)
        user_prompt = self._build_user_prompt(content, prompt, schema)

        # Call LLM
        try:
            extracted = await self._call_llm(system_prompt, user_prompt, correlation_id)
            return ExtractResultItem(url=url, success=True, data=extracted)
        except Exception as e:
            return ExtractResultItem(url=url, success=False, error=str(e))

    def _build_system_prompt(self, schema: dict[str, Any] | None) -> str:
        """Build system prompt for extraction."""
        base = (
            "You are a data extraction assistant. Your task is to extract "
            "structured information from web page content. "
            "Always respond with valid JSON only, no explanations."
        )

        if schema:
            base += f"\n\nOutput must conform to this JSON schema:\n{json.dumps(schema, indent=2)}"

        return base

    def _build_user_prompt(
        self,
        content: str,
        prompt: str | None,
        schema: dict[str, Any] | None,
    ) -> str:
        """Build user prompt for extraction."""
        parts = []

        if prompt:
            parts.append(f"Extraction instructions: {prompt}")

        if schema:
            parts.append("Extract data according to the provided schema.")

        # Limit content to avoid context overflow
        max_content = 50000
        if len(content) > max_content:
            content = content[:max_content] + "\n\n[Content truncated...]"

        parts.append(f"\n\nWeb page content:\n\n{content}")

        return "\n".join(parts)

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Call LLM and parse JSON response."""
        if self._provider == "ollama":
            return await self._call_ollama(system_prompt, user_prompt, correlation_id)
        elif self._provider == "openai":
            return await self._call_openai(system_prompt, user_prompt, correlation_id)
        elif self._provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_prompt, correlation_id)
        else:
            raise ProviderError(
                f"Unsupported provider: {self._provider}",
                provider=self._provider,
                correlation_id=correlation_id,
            )

    async def _call_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Call Ollama via OllamaClient."""
        client = await self._get_ollama_client()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            return await client.chat_json(messages, model=self._model)
        except Exception as e:
            raise ProviderError(
                f"Ollama extraction failed: {e}",
                provider="ollama",
                correlation_id=correlation_id,
                context={"model": self._model, "error": str(e)},
            ) from e

    async def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Call OpenAI API."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError(
                "OPENAI_API_KEY not set",
                provider="openai",
                correlation_id=correlation_id,
            )

        client = await self._get_http_client()

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            "Calling OpenAI API",
            correlation_id=correlation_id,
            model=self._model,
        )

        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        return self._parse_json_response(content, correlation_id)

    async def _call_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Call Anthropic API."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError(
                "ANTHROPIC_API_KEY not set",
                provider="anthropic",
                correlation_id=correlation_id,
            )

        client = await self._get_http_client()

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            "Calling Anthropic API",
            correlation_id=correlation_id,
            model=self._model,
        )

        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self._model,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        response.raise_for_status()

        data = response.json()
        content = data["content"][0]["text"]

        return self._parse_json_response(content, correlation_id)

    def _parse_json_response(
        self,
        content: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Parse JSON from LLM response."""
        content = content.strip()

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                try:
                    return json.loads(content[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Try extracting from generic code block
        if "```" in content:
            start = content.find("```") + 3
            # Skip language identifier if present
            newline = content.find("\n", start)
            if newline > start:
                start = newline + 1
            end = content.find("```", start)
            if end > start:
                try:
                    return json.loads(content[start:end].strip())
                except json.JSONDecodeError:
                    pass

        raise ProviderError(
            f"Failed to parse JSON from response: {content[:200]}...",
            provider=self._provider,
            correlation_id=correlation_id,
            context={"content_preview": content[:200]},
        )
