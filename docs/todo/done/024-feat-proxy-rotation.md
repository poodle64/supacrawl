# 024: Implement Proxy Rotation

## Status

📋 PLANNING

## Problem Summary

The scraper currently supports a single proxy via `CRAWL4AI_PROXY`, but:

1. Single proxy can get blocked
2. No failover when proxy fails
3. No geographic distribution
4. Can't avoid rate limiting across IPs

For scraping at scale or anti-bot heavy sites, proxy rotation is essential.

## Solution Overview

Implement proxy pool and rotation:

1. Support multiple proxy servers
2. Rotate proxies across requests
3. Handle proxy failures with fallback
4. Support proxy authentication
5. Track proxy health and success rates

## Implementation Steps

### Create Proxy Manager Module

- [ ] Create `web_scraper/network/proxy.py`:

```python
from dataclasses import dataclass
from enum import Enum

class ProxyProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"

@dataclass
class Proxy:
    host: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: str | None = None
    password: str | None = None
    
    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

class ProxyRotator:
    """Rotate through proxy pool."""
    
    def __init__(self, proxies: list[Proxy], strategy: str = "round_robin"):
        self._proxies = proxies
        self._strategy = strategy
        self._index = 0
        self._health: dict[str, float] = {}  # Proxy URL -> success rate
    
    def get_proxy(self) -> Proxy | None:
        """Get next proxy based on strategy."""
        if not self._proxies:
            return None
        # Round robin, random, or health-based selection
        ...
    
    def report_success(self, proxy: Proxy) -> None:
        """Report successful request through proxy."""
        ...
    
    def report_failure(self, proxy: Proxy, error: str) -> None:
        """Report failed request through proxy."""
        ...
```

### Configuration Options

- [ ] Support proxy list in config:

```yaml
proxies:
  enabled: true
  rotation: "round_robin"  # round_robin, random, health_based
  list:
    - host: "proxy1.example.com"
      port: 8080
    - host: "proxy2.example.com"
      port: 8080
      username: "user"
      password: "pass"
  file: "proxies.txt"  # Or load from file
  min_success_rate: 0.5  # Remove proxies below this rate
```

- [ ] Environment variable for quick setup:
  - `CRAWL4AI_PROXY_LIST` - Comma-separated proxy URLs
  - `CRAWL4AI_PROXY_FILE` - Path to proxy list file
  - `CRAWL4AI_PROXY_ROTATION` - Rotation strategy

### Integrate with Browser Config

- [ ] Update `build_browser_config()` to use proxy manager
- [ ] Rotate proxy per page or per domain
- [ ] Handle proxy authentication

### Health Tracking

- [ ] Track success/failure rate per proxy
- [ ] Remove proxies below threshold
- [ ] Log proxy health statistics
- [ ] Alert when all proxies are unhealthy

### Failover Handling

- [ ] Retry with different proxy on failure
- [ ] Fallback to direct connection if all proxies fail
- [ ] Configurable retry behavior

## Files to Modify

- Create `web_scraper/network/__init__.py`
- Create `web_scraper/network/proxy.py`
- Update `web_scraper/scrapers/crawl4ai_config.py`
- Update `web_scraper/scrapers/crawl4ai.py`
- Update `web_scraper/models.py` - ProxyConfig
- Update config and docs

## Testing Considerations

- Test round robin rotation
- Test health-based selection
- Test proxy authentication
- Test failover on proxy failure
- Test proxy list file loading
- Mock proxies for unit tests

## Success Criteria

- [ ] Multiple proxies are supported
- [ ] Rotation works correctly
- [ ] Failed proxies are handled
- [ ] Health tracking works
- [ ] Proxy auth is supported
- [ ] Documentation covers proxy options

## References

- Common proxy providers (Bright Data, ScraperAPI, etc.)
- SOCKS5 protocol

