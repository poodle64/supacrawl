"""Common CLI utilities and the main app group."""

import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

console = Console(stderr=True)
_configured = False


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


def configure_logging(*, verbose: bool = False) -> None:
    """Configure logging with Rich handler. Call once at startup."""
    global _configured
    if _configured:
        return

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                tracebacks_show_locals=verbose,
            )
        ],
        force=True,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    _configured = True


@click.group(help="Generic website ingestion pipeline.")
def app() -> None:
    """
    Entry point for the supacrawl CLI.

    Provides commands for scraping, crawling, mapping, searching,
    extracting data, and autonomous web agents.
    """
