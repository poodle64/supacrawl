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
SUPPORTED_PROVIDERS = ("brave", "tavily", "serper", "serpapi", "exa", "duckduckgo", "searxng")

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
    "searxng": "SEARXNG_URL",
}


def create_provider(
    name: str,
    *,
    brave_api_key: str | None = None,
    searxng_username: str | None = None,
    searxng_password: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> SearchProvider:
    """Create a search provider by name.

    Uses lazy imports to avoid loading unused providers.

    Args:
        name: Provider name (must be in SUPPORTED_PROVIDERS).
        brave_api_key: Override for Brave API key (for backwards compat).
        searxng_username: SearXNG HTTP Basic username supplied by the caller
            rather than the environment — the shape a secrets broker vends into.
            Beats SEARXNG_USERNAME and any userinfo left in SEARXNG_URL.
        searxng_password: The matching password, same precedence.
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

    if name == "searxng":
        from supacrawl.services.search.searxng import SearXNGProvider

        return SearXNGProvider(
            http_client=http_client,
            username=searxng_username,
            password=searxng_password,
        )

    raise ValueError(f"Unknown search provider: {name!r}. Supported providers: {', '.join(SUPPORTED_PROVIDERS)}")


def strict_providers_enabled() -> bool:
    """Whether the operator has opted into refusing implicit provider fallback.

    Off by default so a fresh install still answers, on by design for a
    deployment where a query reaching an unconfigured third-party engine is a
    privacy incident rather than an inconvenience (#158).
    """
    return os.getenv("SUPACRAWL_SEARCH_STRICT_PROVIDERS", "").strip().lower() in {"1", "true", "yes", "on"}


def public_fallback_enabled() -> bool:
    """Whether the operator has opted into a public fallback behind a WORKING backend.

    Off by default, and deliberately so. A self-hosted SearXNG is chosen to keep
    queries in-house, so silently answering from DuckDuckGo the moment SearXNG's
    engines flake would betray exactly that intent — a privacy failure, not a
    degradation (#156/#158). By default such a failure surfaces as a loud typed
    error naming the dead engines (#161) instead. An operator who would rather
    have degraded-but-answering search — an OSINT sweep that values a result over
    a clean provenance — sets this to route a failed configured backend on to
    DuckDuckGo. SUPACRAWL_SEARCH_STRICT_PROVIDERS still overrides it to off.
    """
    return os.getenv("SUPACRAWL_SEARCH_PUBLIC_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}


def build_provider_chain(
    providers: str | list[str] | None = None,
    *,
    brave_api_key: str | None = None,
    searxng_username: str | None = None,
    searxng_password: str | None = None,
    http_client: httpx.AsyncClient | None = None,
    strict: bool | None = None,
) -> ProviderChain:
    """Build a provider chain from configuration.

    Args:
        providers: Comma-separated string or list of provider names.
            If None, reads from SUPACRAWL_SEARCH_PROVIDERS env var,
            then falls back to DEFAULT_PROVIDERS.
        brave_api_key: Override for Brave API key.
        searxng_username: SearXNG HTTP Basic username supplied by the caller
            rather than the environment. Beats SEARXNG_USERNAME and any userinfo
            left in SEARXNG_URL.
        searxng_password: The matching password, same precedence.
        http_client: Optional shared HTTP client for providers that accept it.
        strict: When True, never append an unconfigured fallback provider — a
            chain with no usable provider fails loudly at search time instead
            of silently answering from somewhere else. None reads
            SUPACRAWL_SEARCH_STRICT_PROVIDERS.

    Returns:
        Configured ProviderChain. ``chain.configured_names`` records what was
        asked for, so a fallback is always distinguishable from a selection.
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

    chain = ProviderChain(configured_names=list(unique_names))
    for name in unique_names:
        provider = create_provider(
            name,
            brave_api_key=brave_api_key,
            searxng_username=searxng_username,
            searxng_password=searxng_password,
            http_client=http_client,
        )
        chain.add(provider)

    _append_keyless_fallback(chain, unique_names, http_client=http_client, strict=strict)

    available = [p.name for p in chain.providers if p.is_available()]
    LOGGER.debug(f"Search provider chain: {[p.name for p in chain.providers]} (available: {available})")

    return chain


def _append_keyless_fallback(
    chain: ProviderChain,
    configured_names: list[str],
    *,
    http_client: httpx.AsyncClient | None,
    strict: bool | None,
) -> None:
    """Append DuckDuckGo as a keyless last-resort behind the configured chain.

    Two distinct cases, kept apart because their privacy stance differs:

    - **Sole Brave with no key** (default-on): Brave can never answer without a
      key, and it is a third-party API anyway, so a keyless DDG stand-in loses no
      privacy the operator had. Appended unless strict mode refuses it (#158).
      Deliberately NOT triggered when a self-hosted backend (SearXNG) is in the
      configured set — leaking those queries to a public engine is a privacy
      failure, so that case fails loudly instead (#156).

    - **A working backend that fails at runtime** (opt-in, default-off): SearXNG's
      engines going down, a keyed provider's quota exhausted. Routing on to DDG
      here means a configured query leaving in-house, so it is gated on
      SUPACRAWL_SEARCH_PUBLIC_FALLBACK (see ``public_fallback_enabled``) rather
      than done silently — the #161 default is a loud typed error, not a quiet
      leak.

    Never silent (a warning/flag on every result it serves, degraded health) and
    never forced. Skipped when the operator configured DDG themselves.
    """
    if "duckduckgo" in configured_names:
        return

    strict_on = strict if strict is not None else strict_providers_enabled()

    sole_brave_no_key = (
        len(chain.providers) == 1 and chain.providers[0].name == "brave" and not chain.providers[0].is_available()
    )
    if sole_brave_no_key:
        if strict_on:
            LOGGER.error(
                "Brave Search configured but BRAVE_API_KEY is not set, and strict provider mode is on "
                "(SUPACRAWL_SEARCH_STRICT_PROVIDERS). Refusing to fall back to DuckDuckGo — search will "
                "fail loudly until the configured provider is usable."
            )
            return
        LOGGER.warning(
            "SEARCH PROVIDER FALLBACK — configured provider(s) %s cannot be used (BRAVE_API_KEY not set); "
            "falling back to 'duckduckgo', which the operator did NOT configure. Every query will be served "
            "by a public third-party engine until this is fixed. Set BRAVE_API_KEY "
            "(https://brave.com/search/api/), or set SUPACRAWL_SEARCH_STRICT_PROVIDERS=1 to fail instead "
            "of falling back.",
            configured_names,
        )
        chain.add(create_provider("duckduckgo", http_client=http_client))
        return

    # Opt-in runtime fallback behind a configured backend that can actually work.
    any_available = any(p.is_available() for p in chain.providers)
    if any_available and not strict_on and public_fallback_enabled():
        LOGGER.info(
            "SUPACRAWL_SEARCH_PUBLIC_FALLBACK is on — adding DuckDuckGo as a keyless last-resort behind %s. "
            "It serves only if every configured provider fails at runtime (e.g. SearXNG engines down); "
            "queries then leave via a public engine. Unset it to fail loudly instead.",
            configured_names,
        )
        chain.add(create_provider("duckduckgo", http_client=http_client))
