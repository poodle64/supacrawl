"""Health check tool for Supacrawl MCP server."""

import asyncio
import os
from typing import Any

from supacrawl.mcp.config import SERVICE_VERSION, settings
from supacrawl.services.registry import SupacrawlServices

# Query used for the live search probe (#156): short, generic, and cheap for
# every provider (including quota-metered ones) while still exercising the
# real request/response path a config-only check can never catch.
_SEARCH_PROBE_QUERY = "supacrawl health check"
_SEARCH_PROBE_TIMEOUT_S = 15.0


def _get_cache_info() -> dict[str, Any]:
    """Get cache directory statistics if caching is enabled."""
    cache_path = settings.get_cache_path()
    if not cache_path or not cache_path.exists():
        return {"enabled": False}

    try:
        # Count entries and calculate size
        entries = 0
        total_size = 0
        for item in cache_path.rglob("*"):
            if item.is_file():
                entries += 1
                total_size += item.stat().st_size

        return {
            "enabled": True,
            "path": str(cache_path),
            "entries": entries,
            "size_mb": round(total_size / (1024 * 1024), 2),
        }
    except Exception:
        return {"enabled": True, "path": str(cache_path), "error": "could not read stats"}


def _get_llm_config() -> dict[str, Any]:
    """Get LLM configuration status (used for json extraction format)."""
    provider = os.getenv("SUPACRAWL_LLM_PROVIDER")
    model = os.getenv("SUPACRAWL_LLM_MODEL")

    if not provider:
        return {"configured": False}

    return {
        "configured": True,
        "provider": provider,
        "model": model or "default",
    }


def _get_search_config(search_service: Any = None) -> dict[str, Any]:
    """Get search provider configuration and effective runtime state.

    Args:
        search_service: Optional SearchService instance for live provider health.
    """
    from supacrawl.services.search import _PROVIDER_RATE_LIMITS

    has_brave_key = bool(os.getenv("BRAVE_API_KEY"))

    # Determine effective rate limit
    primary_provider = "brave"
    if settings.search_rate_limit is not None:
        rate_limit = settings.search_rate_limit
    else:
        rate_limit = _PROVIDER_RATE_LIMITS.get(primary_provider, 10.0)

    # Provider chain configuration
    configured_providers = settings.search_providers
    if configured_providers:
        provider_list = [p.strip() for p in configured_providers.split(",") if p.strip()]
    else:
        provider_list = [settings.search_provider]

    # Determine overall status
    if search_service and hasattr(search_service, "provider_chain"):
        chain = search_service.provider_chain
        active = chain.active_providers
        provider_health = chain.get_health()

        if active:
            status = "ready"
            effective_provider = active[0].name
        else:
            status = "degraded"
            effective_provider = provider_list[0] if provider_list else "none"
    else:
        provider_health = {}
        # Static check: verify at least one provider has its API key configured
        _provider_key_envs = {
            "brave": "BRAVE_API_KEY",
            "tavily": "TAVILY_API_KEY",
            "serper": "SERPER_API_KEY",
            "serpapi": "SERPAPI_API_KEY",
            "exa": "EXA_API_KEY",
        }
        effective_provider = "none"
        status = "degraded"
        for p in provider_list:
            if p == "duckduckgo":
                # DDG needs no key but is deprecated/unreliable
                if effective_provider == "none":
                    effective_provider = "duckduckgo"
                continue
            env_var = _provider_key_envs.get(p)
            if env_var and bool(os.getenv(env_var)):
                effective_provider = p
                status = "ready"
                break

    config: dict[str, Any] = {
        "configured_providers": provider_list,
        "effective_provider": effective_provider,
        "status": status,
        "brave_api_key_configured": has_brave_key,
        "rate_limit_rps": rate_limit,
    }

    if provider_health:
        config["providers"] = provider_health
        # Surface a low-credit warning at the config level so MCP clients can
        # act on it without needing to inspect the per-provider health dict.
        from supacrawl.services.search.providers import LOW_CREDIT_THRESHOLD, renewal_hint

        low_credit = [
            (name, info["remaining_credits"])
            for name, info in provider_health.items()
            if isinstance(info.get("remaining_credits"), int) and info["remaining_credits"] < LOW_CREDIT_THRESHOLD
        ]
        if low_credit:
            listed = ", ".join(f"{name} ({remaining} left)" for name, remaining in low_credit)
            hints = "; ".join(dict.fromkeys(renewal_hint(name) for name, _ in low_credit))
            config["warning"] = f"Low search credits on: {listed}. {hints} to avoid outages."

    if status == "degraded" and effective_provider == "duckduckgo" and "warning" not in config:
        config["warning"] = (
            "Using DuckDuckGo fallback (deprecated, unreliable). "
            "Set BRAVE_API_KEY for reliable search — see https://brave.com/search/api/"
        )

    return config


async def _run_search_health_probe(search_service: Any) -> dict[str, Any] | None:
    """Run one real, minimal search to verify the effective provider actually returns results.

    ``_get_search_config`` only checks that a provider is *configured* (has a
    URL/API key) — a provider chain can report every provider "available" while
    the underlying search silently returns nothing (#156: SearXNG's multi-word
    query bug went undetected because ``is_available()`` is just ``bool(url)``).
    This runs a single cheap query through the real search path so that class
    of failure surfaces in the health payload instead of reading "healthy".

    Args:
        search_service: The live SearchService, or None if unavailable.

    Returns:
        None when there is no search service to probe. Otherwise a dict with
        ``probed=True``, ``ok`` (whether the probe returned any results), and
        ``result_count`` / ``error`` detail.
    """
    if search_service is None or not hasattr(search_service, "search"):
        return None

    try:
        result = await asyncio.wait_for(
            search_service.search(_SEARCH_PROBE_QUERY, limit=1),
            timeout=_SEARCH_PROBE_TIMEOUT_S,
        )
    except Exception as e:
        return {"probed": True, "ok": False, "result_count": 0, "error": str(e).strip() or type(e).__name__}

    return {
        "probed": True,
        "ok": bool(result.success and result.data),
        "result_count": len(result.data),
        "error": result.error,
    }


def _get_browser_config() -> dict[str, Any]:
    """Get browser configuration."""
    return {
        "headless": settings.headless,
        "timeout_ms": settings.timeout,
        "stealth": settings.stealth,
        "proxy_configured": settings.proxy is not None,
        "locale": settings.locale,
        "timezone": settings.timezone,
    }


def _get_version_info() -> dict[str, str]:
    """Get version information."""
    import supacrawl

    return {
        "supacrawl_lib": supacrawl.__version__,
        "mcp_server": SERVICE_VERSION,  # Now tracks supacrawl lib version
    }


async def supacrawl_health(api_client: SupacrawlServices, verify_search: bool = True) -> dict:
    """Get Supacrawl server health status, search provider state, and credit levels.

    Use this to verify connectivity, check which search provider is active,
    and detect low-credit conditions before they cause search failures.

    Args:
        api_client: Injected SupacrawlServices instance.
        verify_search: When True (default), run one real, minimal search
            through the effective provider chain so a search-path regression
            (provider configured but silently returning nothing — #156) is
            caught here instead of reading "healthy". Set False for a
            config-only check with no live network call.

    Returns:
        Dictionary containing:
        - status: "healthy" | "degraded"
        - components.search: active provider, configured providers, brave_api_key_configured,
          and — when provider health data is available — per-provider remaining_credits
          and last_error. A "warning" key is added when credits are low, DuckDuckGo
          fallback is in use, or the live search probe found no results. A
          "live_probe" key is present only when the probe actually ran (verify_search=True
          and a search service is available), reporting what it found.
        - components.browser: engine, headless, stealth, timeout settings
        - components.llm: configured provider and model (for json/summary formats)
        - components.cache: path, entry count, size
        - version: supacrawl library and MCP server versions
    """
    try:
        service_status = api_client.get_service_status()
        all_healthy = all(service_status.values())

        search_config = _get_search_config(api_client.search_service)
        if verify_search:
            probe = await _run_search_health_probe(api_client.search_service)
            if probe is not None:
                search_config["live_probe"] = probe
                if not probe["ok"]:
                    all_healthy = False
                    search_config["status"] = "degraded"
                    probe_note = (
                        f"Live search probe failed: {probe['error']}"
                        if probe.get("error")
                        else "Live search probe returned no results despite provider configuration appearing ready."
                    )
                    existing_warning = search_config.get("warning")
                    search_config["warning"] = (
                        f"{existing_warning} {probe_note}".strip() if existing_warning else probe_note
                    )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "services": service_status,
            "components": {
                "browser": _get_browser_config(),
                "search": search_config,
                "llm": _get_llm_config(),
                "cache": _get_cache_info(),
            },
            "features": {
                "captcha_solving": settings.solve_captcha,
                "stealth_mode": settings.stealth,
            },
            "version": _get_version_info(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "services": {},
            "version": _get_version_info(),
        }
