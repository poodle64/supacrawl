"""Provider registry and lazy factory.

Maps provider names to their constructors with lazy imports
so unused providers don't add import overhead.
"""

import logging
import os

import httpx

from supacrawl.services.search.providers import ProviderChain, SearchProvider

LOGGER = logging.getLogger(__name__)

# All supported provider names
SUPPORTED_PROVIDERS = ("brave", "tavily", "serper", "serpapi", "exa", "duckduckgo")

# Default provider order when SUPACRAWL_SEARCH_PROVIDERS is not set.
# Just brave (preserving existing default behaviour).
DEFAULT_PROVIDERS = ("brave",)

# API key env var names per provider
_PROVIDER_API_KEY_ENVS: dict[str, str] = {
    "brave": "BRAVE_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "serper": "SERPER_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "exa": "EXA_API_KEY",
}


def create_provider(
    name: str,
    *,
    brave_api_key: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> SearchProvider:
    """Create a search provider by name.

    Uses lazy imports to avoid loading unused providers.

    Args:
        name: Provider name (must be in SUPPORTED_PROVIDERS).
        brave_api_key: Override for Brave API key (for backwards compat).
        http_client: Optional shared HTTP client.

    Returns:
        Instantiated provider.

    Raises:
        ValueError: If provider name is not recognised.
    """
    if name == "brave":
        from supacrawl.services.search.brave import BraveProvider

        return BraveProvider(api_key=brave_api_key, http_client=http_client)

    if name == "duckduckgo":
        from supacrawl.services.search.duckduckgo import DuckDuckGoProvider

        return DuckDuckGoProvider(http_client=http_client)

    if name == "tavily":
        from supacrawl.services.search.tavily import TavilyProvider

        return TavilyProvider()

    if name == "serper":
        from supacrawl.services.search.serper import SerperProvider

        return SerperProvider()

    if name == "serpapi":
        from supacrawl.services.search.serpapi import SerpAPIProvider

        return SerpAPIProvider()

    if name == "exa":
        from supacrawl.services.search.exa import ExaProvider

        return ExaProvider()

    raise ValueError(f"Unknown search provider: {name!r}. Supported providers: {', '.join(SUPPORTED_PROVIDERS)}")


def build_provider_chain(
    providers: str | list[str] | None = None,
    *,
    brave_api_key: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> ProviderChain:
    """Build a provider chain from configuration.

    Args:
        providers: Comma-separated string or list of provider names.
            If None, reads from SUPACRAWL_SEARCH_PROVIDERS env var,
            then falls back to DEFAULT_PROVIDERS.
        brave_api_key: Override for Brave API key.
        http_client: Optional shared HTTP client for providers that accept it.

    Returns:
        Configured ProviderChain.
    """
    # Resolve provider list
    if providers is None:
        env_val = os.getenv("SUPACRAWL_SEARCH_PROVIDERS")
        if env_val:
            provider_names = [p.strip().lower() for p in env_val.split(",") if p.strip()]
        else:
            provider_names = list(DEFAULT_PROVIDERS)
    elif isinstance(providers, str):
        provider_names = [p.strip().lower() for p in providers.split(",") if p.strip()]
    else:
        provider_names = [p.strip().lower() for p in providers]

    # Validate and deduplicate
    seen: set[str] = set()
    unique_names: list[str] = []
    for name in provider_names:
        if name not in SUPPORTED_PROVIDERS:
            LOGGER.warning(f"Unknown search provider {name!r}, skipping")
            continue
        if name in seen:
            continue
        seen.add(name)
        unique_names.append(name)

    if not unique_names:
        LOGGER.warning("No valid providers configured, using defaults")
        unique_names = list(DEFAULT_PROVIDERS)

    chain = ProviderChain()
    for name in unique_names:
        provider = create_provider(name, brave_api_key=brave_api_key, http_client=http_client)
        chain.add(provider)

    # If the only provider is brave and it doesn't have a key, add DDG as fallback
    # (preserves backwards-compatible behaviour)
    if len(chain.providers) == 1 and chain.providers[0].name == "brave" and not chain.providers[0].is_available():
        LOGGER.warning(
            "Brave Search selected but BRAVE_API_KEY not set. "
            "Adding DuckDuckGo as fallback (deprecated, unreliable). "
            "Set BRAVE_API_KEY for reliable search — see https://brave.com/search/api/"
        )
        ddg = create_provider("duckduckgo", http_client=http_client)
        chain.add(ddg)

    available = [p.name for p in chain.providers if p.is_available()]
    LOGGER.debug(f"Search provider chain: {[p.name for p in chain.providers]} (available: {available})")

    return chain
