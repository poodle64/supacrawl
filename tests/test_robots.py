"""Tests for robots.txt parsing and the RFC 9309 longest-match precedence (#119)."""

from supacrawl.discovery.robots import RobotsConfig, is_url_allowed, parse_robots_txt


class TestIsUrlAllowed:
    """URL allow/disallow decisions, including most-specific-match precedence."""

    def test_no_rules_allows_everything(self) -> None:
        assert is_url_allowed("https://example.com/anything", RobotsConfig()) is True

    def test_disallow_blocks_matching_path(self) -> None:
        config = RobotsConfig(disallow_patterns=["/admin"])
        assert is_url_allowed("https://example.com/admin/users", config) is False
        assert is_url_allowed("https://example.com/public", config) is True

    def test_broad_allow_does_not_override_specific_disallow(self) -> None:
        """RFC 9309: ``Allow: /`` must not beat a more-specific ``Disallow: /admin/``."""
        config = RobotsConfig(allow_patterns=["/"], disallow_patterns=["/admin/"])
        assert is_url_allowed("https://example.com/admin/secret", config) is False
        assert is_url_allowed("https://example.com/admin/", config) is False
        # Paths outside the disallow are still allowed.
        assert is_url_allowed("https://example.com/blog/post", config) is True

    def test_specific_allow_overrides_broader_disallow(self) -> None:
        """A longer Allow wins over a shorter Disallow."""
        config = RobotsConfig(allow_patterns=["/private/public"], disallow_patterns=["/private"])
        assert is_url_allowed("https://example.com/private/public/page", config) is True
        assert is_url_allowed("https://example.com/private/secret", config) is False

    def test_equal_length_match_allows(self) -> None:
        """On a tie, Allow wins."""
        config = RobotsConfig(allow_patterns=["/data"], disallow_patterns=["/data"])
        assert is_url_allowed("https://example.com/data/x", config) is True


class TestParseRobotsTxt:
    """End-to-end parse then evaluate."""

    def test_parse_and_enforce_allow_disallow(self) -> None:
        content = "User-agent: *\nAllow: /\nDisallow: /admin/\nCrawl-delay: 3\n"
        config = parse_robots_txt(content)
        assert config.crawl_delay == 3.0
        assert is_url_allowed("https://example.com/admin/panel", config) is False
        assert is_url_allowed("https://example.com/home", config) is True
