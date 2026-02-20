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


def _get_search_config() -> dict[str, Any]:
    """Get search provider configuration."""
    provider = settings.search_provider
    config: dict[str, Any] = {
        "provider": provider,
        "status": "ready",
    }

    # Check if Brave API key is configured (if using Brave)
    if provider == "brave":
        has_key = bool(os.getenv("BRAVE_API_KEY"))
        config["api_key_configured"] = has_key
        if not has_key:
            config["status"] = "missing_api_key"

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
                "search": _get_search_config(),
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
