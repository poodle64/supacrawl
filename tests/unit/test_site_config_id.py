"""Unit tests for SiteConfig id validation and derivation."""

from __future__ import annotations

import pytest

from web_scraper.models import SiteConfig


def _minimal_config_data() -> dict:
    """Return minimal valid site config data (without id)."""
    return {
        "name": "Test Site",
        "entrypoints": ["https://example.com"],
        "include": ["https://example.com/**"],
        "exclude": [],
        "max_pages": 10,
        "formats": ["markdown"],
        "only_main_content": True,
        "include_subdomains": False,
    }


def test_site_config_missing_id_auto_derives_from_context():
    """Test that missing id is auto-derived from expected_id in context."""
    data = _minimal_config_data()
    # No id field in data
    
    config = SiteConfig.model_validate(data, context={"expected_id": "test-site"})
    
    assert config.id == "test-site"


def test_site_config_explicit_matching_id_validates():
    """Test that explicit id matching expected_id validates successfully."""
    data = _minimal_config_data()
    data["id"] = "test-site"
    
    config = SiteConfig.model_validate(data, context={"expected_id": "test-site"})
    
    assert config.id == "test-site"


def test_site_config_explicit_mismatching_id_fails():
    """Test that explicit id not matching expected_id raises ValidationError."""
    from web_scraper.exceptions import ValidationError
    
    data = _minimal_config_data()
    data["id"] = "wrong-site"
    
    with pytest.raises(ValidationError) as exc_info:
        SiteConfig.model_validate(data, context={"expected_id": "test-site"})
    
    assert "must match the filename stem" in str(exc_info.value)
    assert "wrong-site" in str(exc_info.value)
    assert "test-site" in str(exc_info.value)


def test_site_config_missing_id_without_context_fails():
    """Test that missing id without expected_id context raises ValidationError."""
    from web_scraper.exceptions import ValidationError
    
    data = _minimal_config_data()
    # No id field and no context
    
    with pytest.raises(ValidationError) as exc_info:
        SiteConfig.model_validate(data)
    
    assert "must have an 'id' field or be loaded with filename context" in str(exc_info.value)


def test_site_config_with_id_no_context_validates():
    """Test that explicit id without context validates (backwards compatibility)."""
    data = _minimal_config_data()
    data["id"] = "test-site"
    
    # No context provided, but id is explicit
    config = SiteConfig.model_validate(data)
    
    assert config.id == "test-site"

