"""Integration tests for load_site_config with optional id field."""

from __future__ import annotations

from pathlib import Path

import pytest

from supacrawl.exceptions import ConfigurationError
from supacrawl.sites.loader import load_site_config


def test_load_site_config_without_id_derives_from_filename(tmp_path: Path):
    """Test loading config without id field derives it from filename."""
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir()
    
    config_file = sites_dir / "my-site.yaml"
    config_file.write_text("""
name: My Site
entrypoints:
  - https://example.com
include:
  - https://example.com/**
exclude: []
max_pages: 10
formats:
  - markdown
only_main_content: true
include_subdomains: false
""")
    
    config = load_site_config("my-site", sites_dir)
    
    assert config.id == "my-site"
    assert config.name == "My Site"


def test_load_site_config_with_matching_id_validates(tmp_path: Path):
    """Test loading config with id matching filename validates successfully."""
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir()
    
    config_file = sites_dir / "my-site.yaml"
    config_file.write_text("""
id: my-site
name: My Site
entrypoints:
  - https://example.com
include:
  - https://example.com/**
exclude: []
max_pages: 10
formats:
  - markdown
only_main_content: true
include_subdomains: false
""")
    
    config = load_site_config("my-site", sites_dir)
    
    assert config.id == "my-site"
    assert config.name == "My Site"


def test_load_site_config_with_mismatching_id_fails(tmp_path: Path):
    """Test loading config with id not matching filename raises error."""
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir()
    
    config_file = sites_dir / "my-site.yaml"
    config_file.write_text("""
id: wrong-site
name: My Site
entrypoints:
  - https://example.com
include:
  - https://example.com/**
exclude: []
max_pages: 10
formats:
  - markdown
only_main_content: true
include_subdomains: false
""")
    
    # ConfigurationError wraps the ValidationError
    with pytest.raises(ConfigurationError):
        load_site_config("my-site", sites_dir)

