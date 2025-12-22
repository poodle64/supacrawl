"""Load and validate site configuration files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from web_scraper.exceptions import (
    ConfigurationError,
    FileNotFoundError,
    ValidationError,
    generate_correlation_id,
)
from web_scraper.models import SiteConfig
from web_scraper.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


def list_site_configs(sites_dir: Path) -> list[Path]:
    """
    Return all available site configuration files.

    Args:
        sites_dir: Directory containing site configuration YAML files.

    Returns:
        Sorted list of paths to site configuration files.
    """
    if not sites_dir.exists():
        correlation_id = generate_correlation_id()
        log_with_correlation(
            LOGGER,
            logging.WARNING,
            f"Sites directory does not exist: {sites_dir}",
            correlation_id=correlation_id,
            sites_dir=str(sites_dir),
        )
        return []
    return sorted(path for path in sites_dir.glob("*.yaml") if path.is_file())


def _ensure_path(config_name: str | Path, sites_dir: Path) -> Path:
    """
    Resolve a configuration path from a name or path.

    Args:
        config_name: Configuration name (without extension) or path.
        sites_dir: Directory containing site configuration files.

    Returns:
        Resolved path to the configuration file.
    """
    path = Path(config_name)
    if path.suffix == "":
        return sites_dir / f"{path.name}.yaml"
    if not path.is_absolute():
        return sites_dir / path
    return path


def load_site_config(config_name: str | Path, sites_dir: Path) -> SiteConfig:
    """
    Load a site configuration into a SiteConfig model.

    Args:
        config_name: Configuration name (without extension) or path.
        sites_dir: Directory containing site configuration files.

    Returns:
        Validated SiteConfig instance.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ConfigurationError: If the configuration is empty or validation fails.
    """
    correlation_id = generate_correlation_id()
    config_path = _ensure_path(config_name, sites_dir)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Site configuration not found: {config_path}. "
            f"Check that the file exists and the site name is correct.",
            file_path=str(config_path),
            correlation_id=correlation_id,
            context={
                "config_name": str(config_name),
                "sites_dir": str(sites_dir),
                "suggestion": "List available configs with: web-scraper list-sites",
            },
        )

    with config_path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] | None = yaml.safe_load(handle)

    if data is None:
        raise ConfigurationError(
            f"Site configuration is empty: {config_path}. "
            f"The YAML file must contain valid configuration data.",
            config_path=str(config_path),
            correlation_id=correlation_id,
            context={"config_name": str(config_name)},
        )

    # Extract filename stem for id derivation/validation
    expected_id = config_path.stem

    try:
        return SiteConfig.model_validate(data, context={"expected_id": expected_id})
    except PydanticValidationError as exc:
        log_with_correlation(
            LOGGER,
            logging.ERROR,
            f"Validation failed for {config_path}: {exc}",
            correlation_id=correlation_id,
            config_path=str(config_path),
            validation_errors=str(exc),
        )
        raise ConfigurationError(
            f"Site configuration validation failed: {exc}. "
            f"Check that all required fields are present and valid.",
            config_path=str(config_path),
            correlation_id=correlation_id,
            context={"validation_errors": str(exc), "config_name": str(config_name)},
        ) from exc
    except ValidationError as exc:
        # Our custom ValidationError (from model_post_init)
        log_with_correlation(
            LOGGER,
            logging.ERROR,
            f"Validation failed for {config_path}: {exc}",
            correlation_id=exc.correlation_id,
            config_path=str(config_path),
            validation_errors=str(exc),
        )
        raise ConfigurationError(
            f"Site configuration validation failed: {exc.message}",
            config_path=str(config_path),
            correlation_id=exc.correlation_id,
            context={"validation_errors": str(exc), "config_name": str(config_name)},
        ) from exc
