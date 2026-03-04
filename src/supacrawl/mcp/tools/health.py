"""Health check tool for Supacrawl MCP server."""

import os
from typing import Any

from supacrawl.mcp.api_client import SupacrawlServices
from supacrawl.mcp.config import SERVICE_VERSION, settings


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

    if status == "degraded" and effective_provider == "duckduckgo":
        config["warning"] = (
            "Using DuckDuckGo fallback (deprecated, unreliable). "
            "Set BRAVE_API_KEY for reliable search — see https://brave.com/search/api/"
        )

    return config


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


async def supacrawl_health(api_client: SupacrawlServices) -> dict:
    """Get Supacrawl server health status.

    Returns server version, API version, and capabilities.
    Use this for health checks and to verify connectivity.

    Returns:
        Dictionary containing version information:
        - api_version: API version number
        - server_version: Server software version
        - capabilities: Server capabilities
    """
    try:
        service_status = api_client.get_service_status()
        all_healthy = all(service_status.values())

        return {
            "status": "healthy" if all_healthy else "degraded",
            "services": service_status,
            "components": {
                "browser": _get_browser_config(),
                "search": _get_search_config(api_client.search_service),
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
