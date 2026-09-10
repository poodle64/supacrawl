"""Common CLI utilities and the main app group."""

import logging
import os
from importlib.metadata import version
from pathlib import Path

import click

LOGGER = logging.getLogger(__name__)


def _load_env_file(env_path: Path | None = None) -> None:
    """
    Load environment variables from .env file if it exists.

    Args:
        env_path: Optional path to .env file. If None, looks for .env in current directory.
    """
    if env_path is None:
        env_path = Path.cwd() / ".env"

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse key=value pairs
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                # Only set if not already in environment
                if key and key not in os.environ:
                    os.environ[key] = value


# Load .env file when CLI module is imported
_load_env_file()


def configure_logging() -> None:
    """Configure this process's telemetry, once. Call at CLI startup.

    Inside the household (``supacrawl[telemetry]``) the one
    ``api_common.telemetry.configure()`` call owns the log format, the
    redaction floor and the OTLP bootstrap; ``format="auto"`` is text on a
    terminal and JSON the moment output is piped or captured. A plain PyPI
    install carries no api-common and gets the standard library's own
    defaults. Nothing else in this process configures logging.
    """
    try:
        from api_common.telemetry import configure
    except ImportError:
        logging.basicConfig(level=logging.INFO)
        return

    configure(service_name="supacrawl", service_version=version("supacrawl"), format="auto")


def parse_header_string(raw: str) -> tuple[str, str]:
    """Parse a single ``Key: Value`` header string into a (name, value) tuple.

    Splits on the first colon only, so values that contain colons (e.g.
    URLs) are preserved intact.

    Args:
        raw: Header string in ``Key: Value`` format.

    Returns:
        Tuple of (header_name, header_value) with leading/trailing whitespace stripped.

    Raises:
        click.BadParameter: If the string does not contain a colon.
    """
    if ":" not in raw:
        raise click.BadParameter(
            f"Expected 'Key: Value' format but got: {raw!r}. Example: --header 'Authorization: Bearer mytoken'",
            param_hint="'--header'",
        )
    name, _, value = raw.partition(":")
    return name.strip(), value.strip()


def parse_headers_env() -> dict[str, str] | None:
    """Parse ``SUPACRAWL_HEADERS`` environment variable into a headers dict.

    The environment variable is a comma-separated list of ``Key: Value`` pairs.
    Example: ``Authorization: Bearer abc, X-Api-Key: secret``

    Returns:
        Dict of header names to values, or None if the variable is not set or empty.
        Header values that contain colons are preserved intact.
    """
    raw = os.environ.get("SUPACRAWL_HEADERS", "").strip()
    if not raw:
        return None

    headers: dict[str, str] = {}
    # Split on commas that are followed by a key (word chars then colon).
    # A simple split on "," works for the common case; values that legitimately
    # contain commas (rare in HTTP headers) are an edge case not addressed here.
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            LOGGER.debug("Ignoring malformed SUPACRAWL_HEADERS entry (no colon): %r", entry)
            continue
        name, _, value = entry.partition(":")
        headers[name.strip()] = value.strip()

    return headers or None


@click.group(help="Generic website ingestion pipeline.")
@click.version_option(version=version("supacrawl"), prog_name="supacrawl")
def app() -> None:
    """
    Entry point for the supacrawl CLI.

    Provides commands for scraping, crawling, mapping, searching,
    extracting data, and autonomous web agents.
    """
    configure_logging()
