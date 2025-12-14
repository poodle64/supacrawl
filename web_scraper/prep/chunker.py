"""Chunking utilities for LLM-ready corpora."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

import aiofiles

from web_scraper.exceptions import FileNotFoundError, generate_correlation_id
from web_scraper.prep.ollama_client import OllamaClient
from web_scraper.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


def _extract_headings(text: str) -> list[tuple[int, str]]:
    """
    Extract markdown headings from text.

    Args:
        text: Markdown text to parse.

    Returns:
        List of (level, heading_text) tuples.
    """
    headings: list[tuple[int, str]] = []
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            headings.append((level, heading_text))
    return headings


def _get_heading_hierarchy(text: str, position: int) -> list[str]:
    """
    Get the heading hierarchy at a given position in the text.

    Args:
        text: Full markdown text.
        position: Character position in the text.

    Returns:
        List of headings from h1 to current level.
    """
    # Get text before this position
    before_text = text[:position]

    # Find all headings before this position
    headings: dict[int, str] = {}

    for line in before_text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            headings[level] = heading_text
            # Clear lower level headings when a higher level is encountered
            for lower_level in range(level + 1, 7):
                headings.pop(lower_level, None)

    # Build hierarchy from stored headings
    hierarchy: list[str] = []
    for level in sorted(headings.keys()):
        prefix = "#" * level
        hierarchy.append(f"{prefix} {headings[level]}")

    return hierarchy


def _detect_chunk_type(text: str) -> str:
    """
    Detect the primary content type of a chunk.

    Args:
        text: Chunk text to analyse.

    Returns:
        Content type string: 'code', 'list', 'table', 'heading', or 'paragraph'.
    """
    lines = text.strip().splitlines()
    if not lines:
        return "paragraph"

    # Check for code blocks
    if text.strip().startswith("```") or "```" in text:
        return "code"

    # Check for tables
    if any("|" in line and line.count("|") >= 2 for line in lines):
        return "table"

    # Check for lists (more than half of non-empty lines are list items)
    list_pattern = re.compile(r"^\s*[-*+]\s|^\s*\d+\.\s")
    list_lines = sum(1 for line in lines if list_pattern.match(line))
    if list_lines > len(lines) / 2:
        return "list"

    # Check for heading-only chunks
    if len(lines) == 1 and lines[0].strip().startswith("#"):
        return "heading"

    return "paragraph"


def _count_tokens_approx(text: str) -> int:
    """
    Approximate token count for a text.

    Uses a simple heuristic: ~4 characters per token for English text.

    Args:
        text: Text to count tokens for.

    Returns:
        Approximate token count.
    """
    # Rough approximation: 4 chars per token, adjusted for whitespace
    words = len(text.split())
    chars = len(text)
    # Average of word-based and char-based estimates
    return int((words + chars / 4) / 2)


async def _load_manifest(snapshot_path: Path) -> dict:
    """
    Load snapshot manifest data.

    Args:
        snapshot_path: Path to the snapshot directory.

    Returns:
        Manifest data dictionary.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
    """
    manifest_path = snapshot_path / "manifest.json"
    if not manifest_path.exists():
        correlation_id = generate_correlation_id()
        raise FileNotFoundError(
            f"Manifest not found at {manifest_path}. "
            f"Ensure the snapshot directory contains a valid manifest.json file.",
            file_path=str(manifest_path),
            correlation_id=correlation_id,
            context={"snapshot_path": str(snapshot_path)},
        )
    async with aiofiles.open(manifest_path, "r", encoding="utf-8") as handle:
        content = await handle.read()
        return json.loads(content)


async def _load_page_text(snapshot_path: Path, relative_path: str) -> str:
    """
    Load page text from snapshot pages directory.

    Args:
        snapshot_path: Path to the snapshot directory.
        relative_path: Relative path to the page file from snapshot root.

    Returns:
        Page text content.
    """
    page_path = snapshot_path / relative_path
    async with aiofiles.open(page_path, "r", encoding="utf-8") as handle:
        return await handle.read()


def _chunk_text(text: str, max_chars: int) -> list[tuple[str, int]]:
    """
    Split text into sized chunks with position tracking.

    Args:
        text: Text to chunk.
        max_chars: Maximum characters per chunk.

    Returns:
        List of (chunk_text, start_position) tuples.
    """
    chunks: list[tuple[str, int]] = []
    buffer: list[str] = []
    current_len = 0
    buffer_start = 0
    current_pos = 0

    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            current_pos += 2  # Account for the \n\n separator
            continue

        if current_len + len(paragraph) > max_chars and buffer:
            chunks.append(("\n\n".join(buffer), buffer_start))
            buffer = [paragraph]
            buffer_start = current_pos
            current_len = len(paragraph)
        else:
            if not buffer:
                buffer_start = current_pos
            buffer.append(paragraph)
            current_len += len(paragraph)

        current_pos += len(paragraph) + 2  # +2 for \n\n

    if buffer:
        chunks.append(("\n\n".join(buffer), buffer_start))

    return chunks


async def chunk_snapshot(
    snapshot_path: Path,
    max_chars: int = 1200,
    use_ollama: bool = False,
    ollama_model: str | None = None,
    ollama_summarize: bool = False,
) -> Path:
    """
    Create chunked output for a snapshot.

    Args:
        snapshot_path: Path to the snapshot directory.
        max_chars: Maximum characters per chunk. Defaults to 1200.
        use_ollama: Whether to use Ollama for processing. Defaults to False.
        ollama_model: Ollama model to use. Defaults to client default.
        ollama_summarize: Whether to add summaries to chunks using Ollama. Defaults to False.

    Returns:
        Path to the created chunks.jsonl file.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
    """
    correlation_id = generate_correlation_id()
    manifest = await _load_manifest(snapshot_path)
    pages = manifest.get("pages", [])
    chunks_path = snapshot_path / "chunks.jsonl"
    count = 0

    # Initialise Ollama client if needed
    ollama_client: OllamaClient | None = None
    if use_ollama:
        try:
            ollama_client = OllamaClient(model=ollama_model)
            # Check if Ollama is accessible
            if not await ollama_client.check_health():
                log_with_correlation(
                    LOGGER,
                    logging.WARNING,
                    "Ollama server not accessible, continuing without Ollama processing",
                    correlation_id=correlation_id,
                )
                ollama_client = None
        except Exception as exc:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Failed to initialise Ollama client: {exc}, continuing without Ollama processing",
                correlation_id=correlation_id,
                error=str(exc),
            )
            ollama_client = None

    async with aiofiles.open(chunks_path, "w", encoding="utf-8") as handle:
        for page_idx, page in enumerate(pages):
            page_text = await _load_page_text(snapshot_path, page["path"])
            text_chunks = _chunk_text(page_text, max_chars)

            for idx, (chunk_text, chunk_position) in enumerate(text_chunks):
                # Generate unique chunk ID
                chunk_id = f"{manifest['site_id']}-{manifest['snapshot_id']}-{page_idx:04d}-c{idx}"

                # Get heading hierarchy at this position
                heading_hierarchy = _get_heading_hierarchy(page_text, chunk_position)
                parent_heading = heading_hierarchy[-1] if heading_hierarchy else ""

                # Detect chunk type
                chunk_type = _detect_chunk_type(chunk_text)

                # Approximate token count
                token_count = _count_tokens_approx(chunk_text)

                # Content hash for deduplication
                chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()[:16]

                record: dict[str, Any] = {
                    "chunk_id": chunk_id,
                    "site_id": manifest["site_id"],
                    "snapshot_id": manifest["snapshot_id"],
                    "page_url": page["url"],
                    "page_title": page["title"],
                    "chunk_index": idx,
                    "text": chunk_text,
                    "token_count": token_count,
                    "chunk_type": chunk_type,
                    "parent_heading": parent_heading,
                    "heading_hierarchy": heading_hierarchy,
                    "content_hash": chunk_hash,
                }

                # Add language from page metadata if available
                if page.get("language"):
                    record["language"] = page["language"]

                # Add Ollama summarization if enabled
                if ollama_client and ollama_summarize:
                    try:
                        summary = await ollama_client.summarize(chunk_text, model=ollama_model)
                        record["summary"] = summary
                    except Exception as exc:
                        log_with_correlation(
                            LOGGER,
                            logging.WARNING,
                            f"Failed to generate summary for chunk {idx}: {exc}",
                            correlation_id=correlation_id,
                            chunk_index=idx,
                            error=str(exc),
                        )

                await handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    log_with_correlation(
        LOGGER,
        logging.INFO,
        f"Wrote {count} chunks for snapshot {manifest.get('snapshot_id', 'unknown')}",
        correlation_id=correlation_id,
        chunk_count=count,
        snapshot_id=manifest.get("snapshot_id", "unknown"),
        used_ollama=ollama_client is not None,
    )
    return chunks_path
