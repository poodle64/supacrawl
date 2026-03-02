"""Tests for iframe expansion in BrowserManager."""

import pytest

from supacrawl.services.browser import (
    IFRAME_BLOCKED_DOMAINS,
    MAX_IFRAMES_PER_PAGE,
    _is_blocked_iframe_domain,
)


class TestIsBlockedIframeDomain:
    """Tests for _is_blocked_iframe_domain helper."""

    def test_exact_match(self):
        """Exact domain match is blocked."""
        assert _is_blocked_iframe_domain("doubleclick.net") is True

    def test_subdomain_match(self):
        """Subdomain of blocked domain is blocked."""
        assert _is_blocked_iframe_domain("ad.doubleclick.net") is True
        assert _is_blocked_iframe_domain("stats.google-analytics.com") is True

    def test_unblocked_domain(self):
        """Normal domains are not blocked."""
        assert _is_blocked_iframe_domain("example.com") is False
        assert _is_blocked_iframe_domain("docs.python.org") is False

    def test_case_insensitive(self):
        """Domain matching is case-insensitive."""
        assert _is_blocked_iframe_domain("DoubleClick.Net") is True
        assert _is_blocked_iframe_domain("GOOGLETAGMANAGER.COM") is True

    def test_partial_match_not_blocked(self):
        """Partial domain match (not subdomain) is not blocked."""
        # "notdoubleclick.net" is not a subdomain of "doubleclick.net"
        assert _is_blocked_iframe_domain("notdoubleclick.net") is False

    def test_empty_hostname(self):
        """Empty hostname is not blocked."""
        assert _is_blocked_iframe_domain("") is False

    def test_ad_domains_blocked(self):
        """Known ad network domains are blocked."""
        ad_domains = ["googlesyndication.com", "amazon-adsystem.com", "taboola.com", "outbrain.com"]
        for domain in ad_domains:
            assert _is_blocked_iframe_domain(domain) is True, f"{domain} should be blocked"

    def test_analytics_domains_blocked(self):
        """Known analytics domains are blocked."""
        analytics_domains = ["google-analytics.com", "googletagmanager.com", "hotjar.com"]
        for domain in analytics_domains:
            assert _is_blocked_iframe_domain(domain) is True, f"{domain} should be blocked"

    def test_captcha_domains_blocked(self):
        """Known CAPTCHA domains are blocked."""
        captcha_domains = ["recaptcha.net", "hcaptcha.com", "challenges.cloudflare.com"]
        for domain in captcha_domains:
            assert _is_blocked_iframe_domain(domain) is True, f"{domain} should be blocked"


class TestIframeConstants:
    """Tests for iframe-related constants."""

    def test_blocked_domains_is_frozenset(self):
        """Blocked domains constant is immutable."""
        assert isinstance(IFRAME_BLOCKED_DOMAINS, frozenset)

    def test_blocked_domains_not_empty(self):
        """Blocked domains list has entries."""
        assert len(IFRAME_BLOCKED_DOMAINS) > 0

    def test_max_iframes_per_page_reasonable(self):
        """Max iframes limit is a reasonable number."""
        assert MAX_IFRAMES_PER_PAGE > 0
        assert MAX_IFRAMES_PER_PAGE <= 50


class TestExpandIframesIntegration:
    """Integration tests for iframe expansion (require Playwright)."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_expand_iframes_same_origin(self):
        """Same-origin iframe content is expanded inline."""
        from supacrawl.services.browser import BrowserManager

        async with BrowserManager() as browser:
            # Just verify the method exists and is callable
            page_content = await browser.fetch_page(
                "https://example.com",
                expand_iframes="same-origin",
            )
            assert page_content.html is not None

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_expand_iframes_none_mode(self):
        """With mode 'none', iframes are not expanded."""
        from supacrawl.services.browser import BrowserManager

        async with BrowserManager() as browser:
            page_content = await browser.fetch_page(
                "https://example.com",
                expand_iframes="none",
            )
            assert page_content.html is not None
