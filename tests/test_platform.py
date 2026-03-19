"""Tests for platform detection and auto-tuning."""

from supacrawl.services.platform import (
    PLATFORM_PROFILES,
    _detect_foleon,
    detect_platform,
)


class TestFoleonDetection:
    """Tests for Foleon platform detection."""

    def test_detects_foleon_assets_cdn(self):
        html = '<html><head><link href="https://assets.foleon.com/style.css"></head><body></body></html>'
        assert _detect_foleon(html) is True

    def test_detects_foleon_content_class(self):
        html = '<html><body><div class="foleon-content">page</div></body></html>'
        assert _detect_foleon(html) is True

    def test_detects_data_foleon_attribute(self):
        html = '<html><body><div data-foleon="true">page</div></body></html>'
        assert _detect_foleon(html) is True

    def test_detects_fl_class_prefix(self):
        html = '<html><body><div class="fl-page">page</div></body></html>'
        assert _detect_foleon(html) is True

    def test_no_match_on_plain_html(self):
        html = "<html><body><h1>Hello World</h1></body></html>"
        assert _detect_foleon(html) is False

    def test_no_match_on_wordpress(self):
        html = '<html><body class="wp-content"><div class="entry-content">post</div></body></html>'
        assert _detect_foleon(html) is False

    def test_case_insensitive(self):
        html = '<html><head><link href="https://ASSETS.FOLEON.COM/style.css"></head></html>'
        assert _detect_foleon(html) is True


class TestDetectPlatform:
    """Tests for the platform detection registry."""

    def test_returns_foleon_profile(self):
        html = '<html><head><link href="https://assets.foleon.com/x.js"></head><body></body></html>'
        profile = detect_platform(html)
        assert profile is not None
        assert profile.name == "foleon"
        assert profile.engine == "camoufox"
        assert profile.expand_iframes == "all"
        assert profile.wait_for == 8000
        assert profile.only_main_content is False
        assert len(profile.actions) > 0

    def test_returns_none_for_unknown(self):
        html = "<html><body><p>Normal page</p></body></html>"
        assert detect_platform(html) is None


class TestPlatformProfileRegistry:
    """Tests for the registry structure."""

    def test_registry_not_empty(self):
        assert len(PLATFORM_PROFILES) > 0

    def test_all_profiles_have_required_fields(self):
        for profile in PLATFORM_PROFILES:
            assert profile.name
            assert profile.description
            assert profile.examples
            assert callable(profile.detect)

    def test_profile_is_frozen(self):
        profile = PLATFORM_PROFILES[0]
        try:
            profile.name = "changed"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass
