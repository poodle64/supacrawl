"""
Autonomous web agent service for supacrawl.

Navigates the web autonomously to gather data based on a prompt.
Uses LLM for planning and decision making.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any, AsyncGenerator, Literal

import httpx

from supacrawl.exceptions import ProviderError, generate_correlation_id
from supacrawl.models import AgentEvent, AgentResult
from supacrawl.prep.ollama_client import OllamaClient
from supacrawl.utils import log_with_correlation

if TYPE_CHECKING:
    from supacrawl.services.scrape import ScrapeService
    from supacrawl.services.search import SearchService

LOGGER = logging.getLogger(__name__)


class AgentService:
    """
    Autonomous web agent for complex data gathering.

    Combines search, scrape, and extraction to autonomously
    gather data based on natural language prompts.

    Example usage:
        >>> from supacrawl.services.scrape import ScrapeService
        >>> from supacrawl.services.search import SearchService
        >>> scrape_svc = ScrapeService()
        >>> search_svc = SearchService(scrape_service=scrape_svc)
        >>> agent = AgentService(scrape_service=scrape_svc, search_service=search_svc)
        >>> async for event in agent.run("Find AI startups founded in 2024"):
        ...     print(event.type, event.message)
    """

    def __init__(
        self,
        scrape_service: "ScrapeService",
        search_service: "SearchService",
        provider: Literal["ollama", "openai", "anthropic"] = "ollama",
        model: str | None = None,
        ollama_host: str | None = None,
    ):
        """
        Initialise agent service.

        Args:
            scrape_service: ScrapeService for page scraping.
            search_service: SearchService for web search.
            provider: LLM provider ("ollama", "openai", "anthropic").
            model: Model name. Defaults vary by provider.
            ollama_host: Ollama server URL (for ollama provider).
        """
        self._scrape_service = scrape_service
        self._search_service = search_service
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

    async def run(
        self,
        prompt: str,
        urls: list[str] | None = None,
        schema: dict[str, Any] | None = None,
        max_steps: int = 10,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run autonomous agent with given objective.

        Args:
            prompt: Natural language description of data to gather.
            urls: Optional starting URLs to focus on.
            schema: Optional JSON schema for output structure.
            max_steps: Maximum number of steps (pages to visit).

        Yields:
            AgentEvent objects tracking progress.
        """
        correlation_id = generate_correlation_id()
        visited_urls: list[str] = []
        gathered_data: list[dict] = []
        step = 0

        log_with_correlation(
            LOGGER,
            logging.INFO,
            f"Agent starting: {prompt[:100]}...",
            correlation_id=correlation_id,
            max_steps=max_steps,
        )

        try:
            yield AgentEvent(type="thinking", message=f"Understanding objective: {prompt[:100]}...")

            # If no URLs provided, start with a search
            if not urls:
                yield AgentEvent(type="action", message="Searching the web for relevant information...")

                search_query = self._create_search_query(prompt)
                log_with_correlation(
                    LOGGER,
                    logging.DEBUG,
                    f"Searching: {search_query}",
                    correlation_id=correlation_id,
                )

                search_result = await self._search_service.search(
                    query=search_query,
                    limit=5,
                )

                if search_result.success and search_result.data:
                    urls = [r.url for r in search_result.data]
                    yield AgentEvent(
                        type="result",
                        message=f"Found {len(urls)} relevant pages",
                        data={"urls": urls},
                    )
                else:
                    yield AgentEvent(type="error", message="No relevant pages found")
                    return

            # Process each URL
            for url in urls:
                if step >= max_steps:
                    yield AgentEvent(
                        type="thinking",
                        message=f"Reached max steps ({max_steps}), stopping...",
                    )
                    break

                if url in visited_urls:
                    continue

                step += 1
                visited_urls.append(url)

                yield AgentEvent(type="action", message=f"Visiting: {url}", url=url)

                log_with_correlation(
                    LOGGER,
                    logging.DEBUG,
                    f"Scraping step {step}/{max_steps}: {url}",
                    correlation_id=correlation_id,
                )

                # Scrape the page
                scrape_result = await self._scrape_service.scrape(
                    url=url,
                    formats=["markdown"],
                    only_main_content=True,
                )

                if not scrape_result.success or not scrape_result.data:
                    yield AgentEvent(type="error", message=f"Failed to scrape: {url}")
                    continue

                content = scrape_result.data.markdown or ""
                if not content.strip():
                    continue

                # Extract relevant information
                yield AgentEvent(type="thinking", message="Analysing page content...")

                extracted = await self._extract_from_content(
                    content=content,
                    prompt=prompt,
                    schema=schema,
                    url=url,
                    correlation_id=correlation_id,
                )

                if extracted:
                    gathered_data.append({"url": url, **extracted})
                    yield AgentEvent(
                        type="result",
                        message=f"Extracted data from {url}",
                        url=url,
                        data=extracted,
                    )

            # Compile final result
            if schema:
                final_data = await self._compile_results(
                    gathered_data, prompt, schema, correlation_id
                )
            else:
                final_data = {"items": gathered_data}

            log_with_correlation(
                LOGGER,
                logging.INFO,
                f"Agent completed: visited {len(visited_urls)} pages",
                correlation_id=correlation_id,
            )

            yield AgentEvent(
                type="complete",
                message=f"Completed. Visited {len(visited_urls)} pages.",
                data=final_data,
            )

        except Exception as e:
            log_with_correlation(
                LOGGER,
                logging.ERROR,
                f"Agent error: {e}",
                correlation_id=correlation_id,
                error=str(e),
            )
            yield AgentEvent(type="error", message=str(e))

    async def run_sync(
        self,
        prompt: str,
        urls: list[str] | None = None,
        schema: dict[str, Any] | None = None,
        max_steps: int = 10,
    ) -> AgentResult:
        """
        Run agent and return final result.

        Convenience method that consumes all events and returns the final result.

        Args:
            prompt: Natural language description of data to gather.
            urls: Optional starting URLs to focus on.
            schema: Optional JSON schema for output structure.
            max_steps: Maximum number of steps (pages to visit).

        Returns:
            AgentResult with final data.
        """
        visited_urls: list[str] = []
        final_data: dict[str, Any] | None = None
        error: str | None = None

        async for event in self.run(prompt, urls, schema, max_steps):
            if event.url:
                visited_urls.append(event.url)
            if event.type == "complete" and event.data:
                final_data = event.data
            if event.type == "error":
                error = event.message

        if error:
            return AgentResult(
                success=False,
                urls_visited=visited_urls,
                error=error,
            )

        return AgentResult(
            success=True,
            data=final_data,
            urls_visited=visited_urls,
        )

    def _create_search_query(self, prompt: str) -> str:
        """Create search query from prompt."""
        # Simple extraction - remove common instruction words
        query = prompt.lower()
        for word in ["find", "get", "extract", "gather", "collect", "the", "all", "from"]:
            query = query.replace(word, " ")
        return " ".join(query.split())[:100]

    async def _extract_from_content(
        self,
        content: str,
        prompt: str,
        schema: dict[str, Any] | None,
        url: str,
        correlation_id: str,
    ) -> dict[str, Any] | None:
        """Extract relevant data from page content."""
        system_prompt = (
            "You are a data extraction assistant. Extract information relevant "
            "to the user's objective from the provided web page content. "
            "Return a JSON object with the extracted data. "
            "If no relevant information is found, return an empty object {}."
        )

        if schema:
            system_prompt += f"\n\nOutput must conform to this schema:\n{json.dumps(schema, indent=2)}"

        # Limit content to avoid context overflow
        max_content = 30000
        if len(content) > max_content:
            content = content[:max_content] + "\n\n[Content truncated...]"

        user_prompt = f"""
Objective: {prompt}

Source URL: {url}

Web page content:
{content}

Extract relevant information as JSON:
"""

        try:
            return await self._call_llm(system_prompt, user_prompt, correlation_id)
        except Exception as e:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Extraction failed for {url}: {e}",
                correlation_id=correlation_id,
            )
            return None

    async def _compile_results(
        self,
        gathered_data: list[dict],
        prompt: str,
        schema: dict[str, Any],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Compile gathered data into final structured result."""
        if not gathered_data:
            return {}

        system_prompt = (
            "You are a data compilation assistant. Combine the extracted data "
            "from multiple pages into a single structured result. "
            "Deduplicate and merge information as appropriate."
        )

        if schema:
            system_prompt += f"\n\nOutput must conform to this schema:\n{json.dumps(schema, indent=2)}"

        # Limit data size
        data_str = json.dumps(gathered_data, indent=2)
        if len(data_str) > 50000:
            data_str = data_str[:50000] + "\n...[truncated]"

        user_prompt = f"""
Original objective: {prompt}

Data gathered from {len(gathered_data)} pages:
{data_str}

Compile into a single structured result:
"""

        try:
            return await self._call_llm(system_prompt, user_prompt, correlation_id)
        except Exception:
            return {"items": gathered_data}

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
            # Return empty dict as fallback for agent (more lenient than extract)
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Ollama call failed, returning empty: {e}",
                correlation_id=correlation_id,
            )
            return {}

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
            newline = content.find("\n", start)
            if newline > start:
                start = newline + 1
            end = content.find("```", start)
            if end > start:
                try:
                    return json.loads(content[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Agent is more lenient - return empty dict as fallback
        log_with_correlation(
            LOGGER,
            logging.WARNING,
            f"Failed to parse JSON, returning empty: {content[:100]}...",
            correlation_id=correlation_id,
        )
        return {}
