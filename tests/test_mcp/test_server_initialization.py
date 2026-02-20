"""Tests for Supacrawl MCP server initialization."""

import pytest

from supacrawl.mcp.config import SupacrawlSettings, get_settings
from supacrawl.mcp.server import SupacrawlServer


class TestServerInitialization:
    """Test server initialization and configuration."""

    def test_server_creates_with_default_name(self):
        """Server should create with default name 'supacrawl'."""
        server = SupacrawlServer()
        assert server.server_name == "supacrawl"

    def test_server_creates_with_custom_name(self):
        """Server should accept custom name."""
        server = SupacrawlServer(server_name="custom")
        assert server.server_name == "custom"

    def test_server_has_mcp_instance(self):
        """Server should have FastMCP instance."""
        server = SupacrawlServer()
        assert server.mcp is not None

    def test_api_client_initially_none(self):
        """API client should be None before initialization."""
        server = SupacrawlServer()
        assert server.api_client is None


class TestConfiguration:
    """Test configuration loading."""

    def test_settings_loads_defaults(self):
        """Settings should load with defaults."""
        settings = get_settings()
        assert settings.log_level == "INFO"
        assert settings.timeout == 30000
        assert settings.headless is True
        assert settings.wait_until == "domcontentloaded"
        assert settings.search_provider == "duckduckgo"

    def test_settings_validates_log_level(self):
        """Settings should validate log level."""
        settings = SupacrawlSettings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"

    def test_settings_rejects_invalid_log_level(self):
        """Settings should reject invalid log level."""
        with pytest.raises(ValueError, match="Invalid log level"):
            SupacrawlSettings(log_level="INVALID")

    def test_settings_timeout_bounds(self):
        """Settings should enforce timeout bounds."""
        settings = SupacrawlSettings(timeout=60000)
        assert settings.timeout == 60000

    def test_settings_wait_until_validation(self):
        """Settings should validate wait_until values."""
        settings = SupacrawlSettings(wait_until="load")
        assert settings.wait_until == "load"

    def test_settings_rejects_invalid_wait_until(self):
        """Settings should reject invalid wait_until values."""
        with pytest.raises(ValueError, match="Invalid wait_until"):
            SupacrawlSettings(wait_until="invalid")

    def test_settings_has_allowed_origins(self):
        """Settings should have allowed_origins for mcp-common compatibility."""
        settings = get_settings()
        assert hasattr(settings, "allowed_origins")
        assert isinstance(settings.allowed_origins, list)

    def test_settings_has_allowed_hosts(self):
        """Settings should have allowed_hosts for mcp-common compatibility."""
        settings = get_settings()
        assert hasattr(settings, "allowed_hosts")
        assert isinstance(settings.allowed_hosts, list)

    def test_settings_has_service_name(self):
        """Settings should have service_name for mcp-common logging."""
        settings = get_settings()
        assert hasattr(settings, "service_name")
        assert settings.service_name == "supacrawl-mcp"
